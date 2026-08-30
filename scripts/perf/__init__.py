"""Concurrency and performance baseline tooling (CONC-00).

Host-side measurement only. Nothing here is imported by a service; nothing
here changes production concurrency behavior. The service-side counterpart is
`shared.concurrency_probe`, which exposes the same request-class vocabulary as
Prometheus metrics.
"""
