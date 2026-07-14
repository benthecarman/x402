"""Offline Lightning node fakes."""

import hashlib

from x402.mechanisms.bip122 import LightningInvoiceStatus

from .helpers import DEFAULT_CREATED_AT, InvoiceFixture, build_invoice


class FakePayer:
    """Payer returning a configured invoice status."""

    def __init__(self, status: LightningInvoiceStatus) -> None:
        self.status = status
        self.calls: list[tuple[str, str]] = []

    def pay_invoice(self, invoice: str, network: str) -> LightningInvoiceStatus:
        self.calls.append((invoice, network))
        return self.status


class FakeReceiver:
    """Receiver returning a configured invoice."""

    def __init__(self, invoice: str) -> None:
        self.invoice = invoice
        self.create_calls: list[tuple[int, str, int, str]] = []

    def create_invoice(
        self,
        amount_msat: int,
        memo: str,
        expiry_seconds: int,
        network: str,
    ) -> str:
        self.create_calls.append((amount_msat, memo, expiry_seconds, network))
        return self.invoice


class InMemoryLightningNode:
    """Combined payer/receiver node used for core roundtrip tests."""

    def __init__(self, created_at: int = DEFAULT_CREATED_AT) -> None:
        self.created_at = created_at
        self._counter = 0
        self._fixtures: dict[str, InvoiceFixture] = {}

    def create_invoice(
        self,
        amount_msat: int,
        memo: str,
        expiry_seconds: int,
        network: str,
    ) -> str:
        self._counter += 1
        seed = hashlib.sha256(f"x402-{self._counter}".encode()).hexdigest()
        currency = "bc" if "000000000019d668" in network else "tb"
        fixture = build_invoice(
            amount_msat=amount_msat,
            currency=currency,
            preimage=seed,
            created_at=self.created_at,
            expiry_seconds=expiry_seconds,
            description=memo,
        )
        self._fixtures[fixture.invoice] = fixture
        return fixture.invoice

    def pay_invoice(self, invoice: str, network: str) -> LightningInvoiceStatus:
        _ = network
        fixture = self._fixtures[invoice]
        return LightningInvoiceStatus(
            invoice=fixture.invoice,
            payment_hash=fixture.payment_hash,
            amount_msat=fixture.amount_msat,
            status="paid",
            preimage=fixture.preimage,
        )
