"""Tests for the in-memory Lightning settlement store."""

import threading

import x402.mechanisms.bip122.settlement_store as store_module
from x402.mechanisms.bip122 import InMemorySettlementStore


def test_mark_used_is_atomic_under_concurrency() -> None:
    store = InMemorySettlementStore()
    results: list[bool] = []
    barrier = threading.Barrier(8)

    def mark() -> None:
        barrier.wait()
        results.append(store.mark_used("hash", 60))

    threads = [threading.Thread(target=mark) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == 1
    assert results.count(False) == 7


def test_expired_entries_are_pruned(monkeypatch) -> None:
    now = 100.0
    monkeypatch.setattr(store_module.time, "monotonic", lambda: now)
    store = InMemorySettlementStore()
    assert store.mark_used("hash", 10)
    assert store.is_used("hash")

    now = 110.0

    assert store.is_used("hash") is False
    assert store.mark_used("hash", 10) is True
