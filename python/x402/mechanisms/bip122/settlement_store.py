"""Replay protection for Bitcoin Lightning settlements."""

import threading
import time
from typing import Protocol


class SettlementStore(Protocol):
    """Atomic payment-hash replay store.

    ``mark_used`` MUST atomically check and set the key. The in-memory
    implementation is single-process only. Multi-instance deployments MUST use a
    shared atomic store or the same payment can settle once per instance.
    """

    def is_used(self, payment_hash: str) -> bool:
        """Return whether a payment hash has already settled."""
        ...

    def mark_used(self, payment_hash: str, ttl_seconds: int) -> bool:
        """Atomically mark a hash used, returning ``False`` if it already exists."""
        ...


class InMemorySettlementStore:
    """Thread-safe, single-process settlement store with TTL pruning.

    Warning:
        This store does not coordinate across processes or instances. Production
        multi-instance facilitators MUST provide a shared atomic store.
    """

    def __init__(self) -> None:
        self._entries: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_used(self, payment_hash: str) -> bool:
        """Return whether ``payment_hash`` is unexpired and already used."""
        with self._lock:
            self._prune(time.monotonic())
            return payment_hash in self._entries

    def mark_used(self, payment_hash: str, ttl_seconds: int) -> bool:
        """Atomically check and set ``payment_hash`` for ``ttl_seconds``."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        with self._lock:
            now = time.monotonic()
            self._prune(now)
            if payment_hash in self._entries:
                return False
            self._entries[payment_hash] = now + ttl_seconds
            return True

    def _prune(self, now: float) -> None:
        expired = [key for key, deadline in self._entries.items() if deadline <= now]
        for key in expired:
            del self._entries[key]
