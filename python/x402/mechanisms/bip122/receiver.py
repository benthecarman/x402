"""Lightning receiver adapter protocol."""

from typing import Protocol


class LightningReceiver(Protocol):
    """Create BOLT11 invoices through a receiver Lightning node."""

    def create_invoice(
        self,
        amount_msat: int,
        memo: str,
        expiry_seconds: int,
        network: str,
    ) -> str:
        """Create a fresh invoice for an exact millisatoshi amount."""
        ...
