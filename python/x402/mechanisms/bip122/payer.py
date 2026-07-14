"""Lightning payer adapter protocol."""

from typing import Protocol

from .types import LightningInvoiceStatus


class LightningPayer(Protocol):
    """Pay BOLT11 invoices through a payer Lightning node."""

    def pay_invoice(self, invoice: str, network: str) -> LightningInvoiceStatus:
        """Pay an invoice and return its final or retryable state."""
        ...
