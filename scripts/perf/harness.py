"""The concurrency load driver.

One function does the measuring — :func:`run_profile` — and it knows nothing
about HTTP, RabbitMQ, Kafka or Qdrant. It takes an async callable and drives it
at a fixed concurrency. That separation is the point: the driver is exercised
by deterministic in-process fakes in the focused tests, and the same code path
runs against a live Compose stack, so the numbers in an artifact come from
logic that was actually tested.

**Fixed concurrency, not a fixed arrival rate.** The driver runs exactly
`concurrency` workers pulling from a shared counter — a closed-loop load model.
An open-loop model (fire N requests per second regardless of completions) would
answer a different question and, against a saturated stack, would queue
unboundedly inside the harness and report the harness's backlog as the
system's latency. The `CONC-*` track asks "what does this system do with N
concurrent callers", which is the closed-loop question.

**Workers, not N tasks.** Spawning one task per request would put the whole
request set in memory at concurrency 32 and make the early samples measure
task-creation, not the service. `concurrency` long-lived workers keep the
in-flight count exactly at the profile's nominal concurrency.

**Warmup is discarded, not counted.** First calls pay for connection setup,
model load and JIT. Including them turns every profile's p95 into a measure of
cold start.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Sequence

from .runtime import ResourceSampler, monotonic, resource_limitations
from .stats import OutcomeCounts, latency_limitations, summarize_profile

# The concurrency ladder CONC-00 requires. Every later task compares against
# these exact points so profiles line up without interpolation.
DEFAULT_CONCURRENCY_LADDER = (1, 4, 8, 16, 32)

# Wall-clock ceiling for one call before the driver calls it a timeout. Chosen
# above the slowest realistic extended-RAG turn so a slow answer is recorded as
# slow rather than reclassified as a failure.
DEFAULT_CALL_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class CallResult:
    """How one measured call ended.

    `outcome` is one of :data:`perf.stats.OUTCOMES`. A scenario returns
    ``"fallback"`` when the system answered but had to degrade to do it —
    a reranker that replied `busy`, a retrieval that fell back to RRF. The
    driver never infers this; only the scenario can know.
    """

    outcome: str
    latency_seconds: float


# A scenario's measured call. Takes the zero-based index of the call within the
# profile so a scenario can vary its payload deterministically.
CallFn = Callable[[int], Awaitable[CallResult]]


async def _drive_one(call: CallFn, index: int, timeout: float) -> CallResult:
    """Run one call, classifying timeouts and exceptions rather than raising.

    A load driver that propagates the first failure measures nothing about a
    system under stress, which is the only condition worth measuring here.
    """
    started = monotonic()
    try:
        return await asyncio.wait_for(call(index), timeout=timeout)
    except asyncio.TimeoutError:
        return CallResult(outcome="timeout", latency_seconds=monotonic() - started)
    except asyncio.CancelledError:
        raise
    except Exception:
        # The exception's detail belongs in the caller's logs. Here it is one
        # count: an artifact must not grow a field per failure mode.
        return CallResult(outcome="error", latency_seconds=monotonic() - started)


async def _run_calls(
    call: CallFn,
    total: int,
    concurrency: int,
    timeout: float,
    first_index: int = 0,
) -> List[CallResult]:
    """Run `total` calls through exactly `concurrency` workers."""
    if total <= 0:
        return []
    cursor = first_index
    end = first_index + total
    lock = asyncio.Lock()
    results: List[CallResult] = []

    async def worker() -> None:
        nonlocal cursor
        while True:
            async with lock:
                if cursor >= end:
                    return
                index = cursor
                cursor += 1
            result = await _drive_one(call, index, timeout)
            results.append(result)

    await asyncio.gather(*(worker() for _ in range(min(concurrency, total))))
    return results


async def run_profile(
    call: CallFn,
    concurrency: int,
    total_requests: int,
    warmup_requests: int = 0,
    call_timeout_seconds: float = DEFAULT_CALL_TIMEOUT_SECONDS,
    sample_resources: bool = True,
) -> Dict[str, object]:
    """Drive one load profile and return its metric summary.

    Args:
        call: The scenario's measured call.
        concurrency: Nominal in-flight callers. Also the worker count.
        total_requests: Measured calls, excluding warmup.
        warmup_requests: Calls run and discarded before measurement begins.
        call_timeout_seconds: Per-call ceiling; an expiry counts as a timeout.
        sample_resources: Sample host CPU/RAM for the measured window only.

    Returns:
        The profile section of a baseline artifact: nominal concurrency,
        request/duration/throughput, latency distribution, outcome counts,
        resource summary and the limitations those figures carry.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    # Warmup runs at the profile's own concurrency: warming at concurrency 1
    # would leave a pool sized for one caller and charge the first measured
    # requests for growing it.
    await _run_calls(call, warmup_requests, concurrency, call_timeout_seconds)

    sampler = ResourceSampler()
    if sample_resources:
        sampler.start()
    started = monotonic()
    results = await _run_calls(
        call,
        total_requests,
        concurrency,
        call_timeout_seconds,
        first_index=warmup_requests,
    )
    duration = monotonic() - started
    sampler.stop()

    outcomes = OutcomeCounts()
    for result in results:
        outcomes.record(result.outcome)

    # Latency is summarized over calls that produced an answer. A timeout's
    # latency is the timeout value by construction, so mixing it in would drag
    # every percentile toward the ceiling and describe the harness's own
    # setting rather than the system.
    latencies = [r.latency_seconds for r in results if r.outcome in ("success", "fallback")]

    summary = summarize_profile(latencies, outcomes, duration)
    summary["concurrency"] = concurrency
    summary["warmup_requests"] = warmup_requests
    summary["resources"] = sampler.summary() if sample_resources else None
    summary["limitations"] = [
        *latency_limitations(latencies),
        *(resource_limitations() if sample_resources else []),
    ]
    return summary


async def run_ladder(
    call: CallFn,
    concurrency_ladder: Sequence[int] = DEFAULT_CONCURRENCY_LADDER,
    requests_per_profile: int = 100,
    warmup_requests: int = 10,
    call_timeout_seconds: float = DEFAULT_CALL_TIMEOUT_SECONDS,
    stop_on_saturation: Optional[Callable[[Dict[str, object]], bool]] = None,
) -> List[Dict[str, object]]:
    """Run one scenario across the concurrency ladder, lowest first.

    Args:
        stop_on_saturation: Consulted after each profile. Returning True stops
            the ladder. GPU-backed paths use this to stop climbing once the
            configured runtime is clearly saturated — CONC-00 asks for evidence,
            not for an OOM'd accelerator.

    Returns:
        One profile summary per concurrency point actually run. A ladder cut
        short is visible as a shorter list, never as fabricated entries.
    """
    profiles: List[Dict[str, object]] = []
    for concurrency in concurrency_ladder:
        profile = await run_profile(
            call,
            concurrency=concurrency,
            total_requests=requests_per_profile,
            warmup_requests=warmup_requests,
            call_timeout_seconds=call_timeout_seconds,
        )
        profiles.append(profile)
        if stop_on_saturation is not None and stop_on_saturation(profile):
            notes = profile["limitations"]
            assert isinstance(notes, list)  # run_profile always sets this
            notes.append(
                "ladder stopped here: the configured runtime was saturated, so "
                "higher concurrency points were not measured"
            )
            break
    return profiles
