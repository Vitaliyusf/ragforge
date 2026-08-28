"""Cross-service contracts and infrastructure primitives.

Import from the owning submodule so importing :mod:`shared` never initializes
metrics, resilience primitives, or other process-global infrastructure.
"""
