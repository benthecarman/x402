"""Bitcoin Lightning payload and adapter types."""

from dataclasses import dataclass
from typing import Any, Literal

LightningPaymentStatus = Literal["unpaid", "in_flight", "paid"]


@dataclass(frozen=True)
class LightningInvoiceStatus:
    """Invoice state returned by a payer adapter.

    Payer adapters MUST set ``preimage`` when ``status`` is ``"paid"``.
    """

    invoice: str
    payment_hash: str
    amount_msat: int
    status: LightningPaymentStatus
    preimage: str | None = None


@dataclass(frozen=True)
class ExactBip122Payload:
    """Exact Lightning payment proof."""

    preimage: str

    def to_dict(self) -> dict[str, Any]:
        """Return the wire payload."""
        return {"preimage": self.preimage}
