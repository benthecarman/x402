"""Signed BOLT11 fixtures for Bitcoin Lightning mechanism tests."""

import hashlib
from dataclasses import dataclass

from bolt11 import Bolt11, MilliSatoshi, Tags, encode

from x402.mechanisms.bip122 import (
    ASSET_BTC,
    BITCOIN_MAINNET_CAIP2,
    PAY_TO_MERCHANT,
    PAYMENT_METHOD_LIGHTNING,
    SCHEME_EXACT,
)
from x402.schemas import PaymentPayload, PaymentRequirements

PRIVATE_KEY = "12" * 32
PAYMENT_SECRET = "34" * 32
DEFAULT_PREIMAGE = "0001020304050607080900010203040506070809000102030405060708090102"
DEFAULT_CREATED_AT = 2_000_000_000


@dataclass(frozen=True)
class InvoiceFixture:
    """A signed invoice and its proof fields."""

    invoice: str
    preimage: str
    payment_hash: str
    amount_msat: int
    currency: str
    created_at: int
    expiry_seconds: int


def build_invoice(
    amount_msat: int = 21_000,
    currency: str = "bc",
    preimage: str = DEFAULT_PREIMAGE,
    created_at: int = DEFAULT_CREATED_AT,
    expiry_seconds: int = 300,
    description: str = "x402 payment",
) -> InvoiceFixture:
    """Construct a genuinely signed BOLT11 invoice with controllable fields."""
    payment_hash = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
    tags = Tags.from_dict(
        {
            "payment_hash": payment_hash,
            "payment_secret": PAYMENT_SECRET,
            "description": description,
            "expire_time": expiry_seconds,
            "min_final_cltv_expiry": 18,
        }
    )
    invoice = encode(
        Bolt11(
            currency=currency,
            amount_msat=MilliSatoshi(amount_msat),
            date=created_at,
            tags=tags,
        ),
        private_key=PRIVATE_KEY,
        strict=True,
    )
    return InvoiceFixture(
        invoice=invoice,
        preimage=preimage,
        payment_hash=payment_hash,
        amount_msat=amount_msat,
        currency=currency,
        created_at=created_at,
        expiry_seconds=expiry_seconds,
    )


def build_requirements(
    fixture: InvoiceFixture,
    *,
    network: str = BITCOIN_MAINNET_CAIP2,
    scheme: str = SCHEME_EXACT,
    asset: str = ASSET_BTC,
    pay_to: str = PAY_TO_MERCHANT,
    payment_method: str = PAYMENT_METHOD_LIGHTNING,
) -> PaymentRequirements:
    """Construct valid Lightning payment requirements."""
    return PaymentRequirements(
        scheme=scheme,
        network=network,
        amount=str(fixture.amount_msat),
        asset=asset,
        pay_to=pay_to,
        max_timeout_seconds=fixture.expiry_seconds,
        extra={"paymentMethod": payment_method, "invoice": fixture.invoice},
    )


def build_payload(
    fixture: InvoiceFixture,
    requirements: PaymentRequirements | None = None,
) -> tuple[PaymentPayload, PaymentRequirements]:
    """Construct a valid payment payload and independent requirements copy."""
    requirements = requirements or build_requirements(fixture)
    accepted = requirements.model_copy(deep=True)
    payload = PaymentPayload(
        x402_version=2,
        accepted=accepted,
        payload={"preimage": fixture.preimage},
    )
    return payload, requirements
