"""Latency and outcome summaries for the concurrency baseline.

Deliberately dependency-free and pure: given the same samples it produces the
same summary on any machine, which is what lets a `CONC-*` task compare its
numbers against a baseline someone else recorded.

Two rules from `docs/ai/BENCHMARKING.md` are enforced here rather than left to
whoever reads the artifact:

**A percentile nobody can support is ``None``.** p99 needs enough samples for
the 99th to mean something; below :data:`P99_MIN_SAMPLES` the single slowest
sample *is* the p99 and reporting it invites a comparison between two numbers
that are really one outlier each. It is recorded as ``None`` with the reason
stated in the artifact's limitations.

**Throughput is achieved, not requested.** It is measured completions over
measured wall-clock, so a profile that failed half its requests cannot report
the rate it was aiming for.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

# Below this, the 99th percentile is just "the slowest sample" wearing a
# statistical name. 100 is the smallest count at which nearest-rank p99 stops
# being definitionally the maximum.
P99_MIN_SAMPLES = 100

# The four ways a measured call can end. `fallback` is a success the system
# had to degrade to reach — counting it as a plain success is exactly how a
# reranker that started answering `busy` under load stays invisible.
OUTCOMES = ("success", "error", "timeout", "fallback")


def percentile(samples: Sequence[float], fraction: float) -> Optional[float]:
    """Nearest-rank percentile of `samples`, or ``None`` when empty.

    Nearest-rank rather than interpolated: it always returns a value that was
    actually observed, so a p95 in an artifact can be traced back to a real
    request instead of to arithmetic between two of them.
    """
    if not samples:
        return None
    ordered = sorted(samples)
    rank = max(1, min(len(ordered), int(-(-fraction * len(ordered) // 1))))
    return ordered[rank - 1]


@dataclass(frozen=True)
class LatencySummary:
    """Latency distribution for one load profile, in seconds."""

    count: int
    mean: Optional[float]
    minimum: Optional[float]
    maximum: Optional[float]
    p50: Optional[float]
    p95: Optional[float]
    p99: Optional[float]

    @classmethod
    def from_samples(cls, samples: Sequence[float]) -> "LatencySummary":
        if not samples:
            return cls(count=0, mean=None, minimum=None, maximum=None, p50=None, p95=None, p99=None)
        return cls(
            count=len(samples),
            mean=sum(samples) / len(samples),
            minimum=min(samples),
            maximum=max(samples),
            p50=percentile(samples, 0.50),
            p95=percentile(samples, 0.95),
            # Withheld rather than guessed — see P99_MIN_SAMPLES.
            p99=percentile(samples, 0.99) if len(samples) >= P99_MIN_SAMPLES else None,
        )

    def as_dict(self) -> Dict[str, Optional[float]]:
        return {
            "count": self.count,
            "mean_seconds": self.mean,
            "min_seconds": self.minimum,
            "max_seconds": self.maximum,
            "p50_seconds": self.p50,
            "p95_seconds": self.p95,
            "p99_seconds": self.p99,
        }


@dataclass
class OutcomeCounts:
    """How the calls in one load profile ended."""

    counts: Dict[str, int] = field(default_factory=lambda: {name: 0 for name in OUTCOMES})

    def record(self, outcome: str) -> None:
        if outcome not in self.counts:
            raise ValueError(f"unknown outcome {outcome!r}; expected one of {OUTCOMES}")
        self.counts[outcome] += 1

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def completed(self) -> int:
        """Calls that produced an answer, degraded or not."""
        return self.counts["success"] + self.counts["fallback"]

    def as_dict(self) -> Dict[str, int]:
        return dict(self.counts)


def achieved_throughput(completed: int, duration_seconds: float) -> Optional[float]:
    """Completions per second, or ``None`` when the duration is unusable.

    A zero or negative duration means the clock, not the system, so no rate is
    reported — an infinite throughput in an artifact is worse than a gap.
    """
    if duration_seconds <= 0:
        return None
    return completed / duration_seconds


def summarize_profile(
    latencies: Sequence[float],
    outcomes: OutcomeCounts,
    duration_seconds: float,
) -> Dict[str, object]:
    """Assemble one profile's metric summary in artifact shape."""
    summary = LatencySummary.from_samples(latencies)
    return {
        "requests": outcomes.total,
        "duration_seconds": duration_seconds,
        "achieved_throughput_per_second": achieved_throughput(
            outcomes.completed, duration_seconds
        ),
        "latency": summary.as_dict(),
        "outcomes": outcomes.as_dict(),
    }


def latency_limitations(latencies: Sequence[float]) -> List[str]:
    """Limitations this sample count forces on the numbers above."""
    if len(latencies) < P99_MIN_SAMPLES:
        return [
            f"p99 withheld: {len(latencies)} samples is below the "
            f"{P99_MIN_SAMPLES}-sample floor where nearest-rank p99 stops "
            "being the maximum"
        ]
    return []
