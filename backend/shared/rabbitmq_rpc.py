"""Bounded, multiplexed RabbitMQ RPC transport shared by service clients."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import uuid4

import aio_pika
import aio_pika.abc

from .auth import attach_internal_auth_context, verify_internal_ticket_from_envelope
from .metrics import METRICS, traffic_class


StreamCallback = Callable[[Dict[str, Any]], Awaitable[None]]


@dataclass
class _Waiter:
    future: asyncio.Future[Dict[str, Any]]
    stream_queue: Optional[asyncio.Queue[Dict[str, Any]]] = None
    stream_task: Optional[asyncio.Task[None]] = None


class MultiplexedRabbitMQRPCClient:
    """Reuse one callback queue and correlate many bounded concurrent calls."""

    def __init__(
        self,
        url: str,
        exchange_name: str,
        service_name: str,
        *,
        max_inflight: int = 64,
        stream_drain_timeout: float = 1.0,
        stream_buffer_size: int = 256,
        record_metrics: bool = True,
    ) -> None:
        self._url = url
        self._exchange_name = exchange_name
        self._service_name = service_name
        self._stream_drain_timeout = stream_drain_timeout
        self._stream_buffer_size = stream_buffer_size
        self._record_metrics = record_metrics
        self._connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
        self._channel: Optional[aio_pika.abc.AbstractChannel] = None
        self._exchange: Optional[aio_pika.abc.AbstractExchange] = None
        self._reply_queue: Optional[aio_pika.abc.AbstractQueue] = None
        self._consumer_tag: Optional[str] = None
        self._stream_routing_key = f"rpc.stream.{service_name}.{uuid4().hex}"
        self._waiters: Dict[str, _Waiter] = {}
        self._resource_lock = asyncio.Lock()
        self._inflight = asyncio.Semaphore(max(1, max_inflight))
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread_id: Optional[int] = None
        self._closed = False

    @property
    def waiter_count(self) -> int:
        return len(self._waiters)

    @property
    def reply_queue_name(self) -> Optional[str]:
        return self._reply_queue.name if self._reply_queue is not None else None

    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    async def connect(self) -> None:
        """Create the reusable topology, or recreate it after a hard close."""
        self._closed = False
        await self._ensure_resources()

    async def _ensure_resources(self) -> None:
        if self._closed:
            raise RuntimeError("RabbitMQ RPC client is closed")
        if (
            self._connection is not None
            and not self._connection.is_closed
            and self._channel is not None
            and not self._channel.is_closed
            and self._exchange is not None
            and self._reply_queue is not None
        ):
            return

        async with self._resource_lock:
            if self._closed:
                raise RuntimeError("RabbitMQ RPC client is closed")
            if (
                self._connection is not None
                and not self._connection.is_closed
                and self._channel is not None
                and not self._channel.is_closed
                and self._exchange is not None
                and self._reply_queue is not None
            ):
                return

            connection = self._connection
            if connection is None or connection.is_closed:
                connection = await aio_pika.connect_robust(self._url)
                self._connection = connection

            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            reply_queue = await channel.declare_queue(
                exclusive=True,
                auto_delete=True,
            )
            await reply_queue.bind(
                exchange,
                routing_key=self._stream_routing_key,
            )
            consumer_tag = await reply_queue.consume(self._on_message)

            self._channel = channel
            self._exchange = exchange
            self._reply_queue = reply_queue
            self._consumer_tag = consumer_tag
            self._loop = asyncio.get_running_loop()
            self._loop_thread_id = threading.get_ident()

    async def publish(
        self,
        routing_key: str,
        envelope: Dict[str, Any],
        *,
        auth_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Publish without allocating request-scoped transport resources."""
        await self._ensure_resources()
        assert self._exchange is not None
        body = attach_internal_auth_context(dict(envelope), **(auth_kwargs or {}))
        await self._exchange.publish(
            aio_pika.Message(
                body=json.dumps(body).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )

    async def request(
        self,
        routing_key: str,
        envelope: Dict[str, Any],
        *,
        timeout: float,
        auth_kwargs: Optional[Dict[str, Any]] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> Dict[str, Any]:
        """Publish one call and route its reply by correlation id."""
        await self._inflight.acquire()
        downstream = routing_key
        gauge = None
        if self._record_metrics:
            gauge = METRICS.rpc_inflight.labels(service=self._service_name, downstream=downstream)
            gauge.inc()
        started = time.perf_counter()
        correlation_id = ""
        waiter: Optional[_Waiter] = None
        try:
            await self._ensure_resources()
            assert self._exchange is not None
            assert self._reply_queue is not None

            body = dict(envelope)
            # The envelope's caller correlation may be shared by several
            # downstream calls in one request. RPC correlation is hop-local and
            # must be unique or one concurrent call could replace another's
            # waiter. request_id/trace_id retain end-to-end context.
            correlation_id = uuid4().hex
            body["correlation_id"] = correlation_id
            body["reply_to"] = self._reply_queue.name
            if stream_callback is not None:
                body["stream_to"] = self._stream_routing_key
            body = attach_internal_auth_context(body, **(auth_kwargs or {}))

            loop = asyncio.get_running_loop()
            waiter = _Waiter(future=loop.create_future())
            if stream_callback is not None:
                waiter.stream_queue = asyncio.Queue(maxsize=self._stream_buffer_size)
                waiter.stream_task = asyncio.create_task(
                    self._run_stream(waiter.stream_queue, stream_callback),
                    name=f"rpc-stream-{correlation_id}",
                )
            self._waiters[correlation_id] = waiter

            await self._exchange.publish(
                aio_pika.Message(
                    body=json.dumps(body).encode("utf-8"),
                    correlation_id=correlation_id,
                    reply_to=self._reply_queue.name,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=routing_key,
            )

            try:
                async with asyncio.timeout(timeout):
                    reply = await asyncio.shield(waiter.future)
            except TimeoutError as exc:
                if self._record_metrics:
                    METRICS.rpc_timeouts_total.labels(
                        service=self._service_name,
                        downstream=downstream,
                    ).inc()
                raise TimeoutError(
                    f"RabbitMQ RPC timeout waiting for '{routing_key}' after {timeout:.1f}s"
                ) from exc

            if self._record_metrics:
                METRICS.rpc_roundtrip_seconds.labels(
                    service=self._service_name,
                    downstream=downstream,
                    traffic_class=traffic_class(),
                ).observe(time.perf_counter() - started)

            if waiter.stream_task is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(waiter.stream_task),
                        timeout=self._stream_drain_timeout,
                    )
                except asyncio.TimeoutError:
                    waiter.stream_task.cancel()
                    await asyncio.gather(waiter.stream_task, return_exceptions=True)
            return reply
        finally:
            if correlation_id:
                current = self._waiters.get(correlation_id)
                if current is waiter:
                    self._waiters.pop(correlation_id, None)
            if waiter is not None:
                if not waiter.future.done():
                    waiter.future.cancel()
                if waiter.stream_task is not None and not waiter.stream_task.done():
                    waiter.stream_task.cancel()
                    await asyncio.gather(waiter.stream_task, return_exceptions=True)
            if gauge is not None:
                gauge.dec()
            self._inflight.release()

    def request_from_thread(
        self,
        routing_key: str,
        envelope: Dict[str, Any],
        *,
        timeout: float,
        auth_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Bridge a synchronous worker-thread caller onto the owner loop."""
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("RabbitMQ RPC client event loop is not running")
        if threading.get_ident() == self._loop_thread_id:
            raise RuntimeError("synchronous RabbitMQ RPC cannot block its owner event loop")
        future = asyncio.run_coroutine_threadsafe(
            self.request(
                routing_key,
                envelope,
                timeout=timeout,
                auth_kwargs=auth_kwargs,
            ),
            self._loop,
        )
        return future.result(timeout=timeout + 1.0)

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with message.process():
            payload = json.loads(message.body)
            if not isinstance(payload, dict):
                return
            correlation_id = str(message.correlation_id or payload.get("correlation_id") or "")
            waiter = self._waiters.get(correlation_id)
            if waiter is None:
                return
            try:
                verify_internal_ticket_from_envelope(payload, required=True)
            except Exception as exc:
                if not waiter.future.done():
                    waiter.future.set_exception(exc)
                return

            if payload.get("message_type") == "stream_event":
                if waiter.stream_queue is None:
                    return
                try:
                    waiter.stream_queue.put_nowait(payload)
                except asyncio.QueueFull:
                    if not waiter.future.done():
                        waiter.future.set_exception(RuntimeError("RabbitMQ RPC stream buffer is full"))
                return

            if not waiter.future.done():
                waiter.future.set_result(payload)

    async def _run_stream(
        self,
        queue: asyncio.Queue[Dict[str, Any]],
        callback: StreamCallback,
    ) -> None:
        while True:
            event = await queue.get()
            await callback(event)
            payload = event.get("payload")
            event_type = payload.get("event_type") if isinstance(payload, dict) else None
            if event_type in {"llm.done", "llm.error"}:
                return

    async def close(self) -> None:
        """Fail outstanding calls, cancel streams, then close owned resources."""
        self._closed = True
        waiters = list(self._waiters.values())
        self._waiters.clear()
        for waiter in waiters:
            if not waiter.future.done():
                waiter.future.set_exception(RuntimeError("RabbitMQ RPC client closed"))
            if waiter.stream_task is not None and not waiter.stream_task.done():
                waiter.stream_task.cancel()
        tasks = [waiter.stream_task for waiter in waiters if waiter.stream_task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self._reply_queue is not None and self._consumer_tag is not None:
            with suppress(Exception):
                await self._reply_queue.cancel(self._consumer_tag)
        if self._channel is not None and not self._channel.is_closed:
            with suppress(Exception):
                await self._channel.close()
        if self._connection is not None and not self._connection.is_closed:
            with suppress(Exception):
                await self._connection.close()
        self._consumer_tag = None
        self._reply_queue = None
        self._exchange = None
        self._channel = None
        self._connection = None
        self._loop = None
        self._loop_thread_id = None
