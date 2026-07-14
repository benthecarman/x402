"""Tests for the exact BIP-122 client scheme."""

from dataclasses import replace

import pytest

from x402.mechanisms.bip122 import (
    BITCOIN_MAINNET_CAIP2,
    ERR_INVALID_MAX_TIMEOUT,
    ERR_INVOICE_AMOUNT_MISMATCH,
    ERR_INVOICE_CREATED_IN_FUTURE,
    ERR_INVOICE_EXPIRY_MISMATCH,
    ERR_INVOICE_MISSING,
    ERR_PAY_TO_MISMATCH,
    ERR_PAYER_INVOICE_MISMATCH,
    ERR_PAYER_PREIMAGE_HASH_MISMATCH,
    ERR_PAYER_PREIMAGE_MALFORMED,
    ERR_PAYER_PREIMAGE_REQUIRED,
    ERR_PAYMENT_IN_FLIGHT,
    ERR_PAYMENT_METHOD,
    ERR_PAYMENT_NOT_PAID,
    ERR_UNSUPPORTED_SCHEME,
    ExactBip122ClientScheme,
    LightningInvoiceStatus,
)

from .fakes import FakePayer
from .helpers import DEFAULT_CREATED_AT, build_invoice, build_requirements


def paid_status(fixture) -> LightningInvoiceStatus:
    """Return a valid paid payer response."""
    return LightningInvoiceStatus(
        invoice=fixture.invoice,
        payment_hash=fixture.payment_hash,
        amount_msat=fixture.amount_msat,
        status="paid",
        preimage=fixture.preimage,
    )


def test_happy_path_returns_preimage() -> None:
    fixture = build_invoice()
    payer = FakePayer(paid_status(fixture))

    result = ExactBip122ClientScheme(payer).create_payment_payload(build_requirements(fixture))

    assert result == {"preimage": fixture.preimage}
    assert payer.calls == [(fixture.invoice, BITCOIN_MAINNET_CAIP2)]


def test_missing_invoice_is_rejected() -> None:
    fixture = build_invoice()
    requirements = build_requirements(fixture)
    requirements.extra.pop("invoice")

    with pytest.raises(ValueError, match=ERR_INVOICE_MISSING):
        ExactBip122ClientScheme(FakePayer(paid_status(fixture))).create_payment_payload(
            requirements
        )


def test_payer_invoice_mismatch_is_rejected() -> None:
    fixture = build_invoice()
    payer = FakePayer(replace(paid_status(fixture), invoice="different"))

    with pytest.raises(ValueError, match=ERR_PAYER_INVOICE_MISMATCH):
        ExactBip122ClientScheme(payer).create_payment_payload(build_requirements(fixture))


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("scheme", "upto", ERR_UNSUPPORTED_SCHEME),
        ("payment_method", "onchain", ERR_PAYMENT_METHOD),
    ],
)
def test_wrong_scheme_or_method_is_rejected(field: str, value: str, reason: str) -> None:
    fixture = build_invoice()
    requirements = build_requirements(fixture)
    if field == "scheme":
        requirements.scheme = value
    else:
        requirements.extra["paymentMethod"] = value

    with pytest.raises(ValueError, match=reason):
        ExactBip122ClientScheme(FakePayer(paid_status(fixture))).create_payment_payload(
            requirements
        )


def test_invoice_amount_mismatch_is_rejected_before_payment() -> None:
    fixture = build_invoice(amount_msat=21_000)
    requirements = build_requirements(fixture)
    requirements.amount = "22000"
    payer = FakePayer(paid_status(fixture))

    with pytest.raises(ValueError, match=ERR_INVOICE_AMOUNT_MISMATCH):
        ExactBip122ClientScheme(payer).create_payment_payload(requirements)

    assert payer.calls == []


@pytest.mark.parametrize(
    ("max_timeout_seconds", "created_at", "reason"),
    [
        (0, DEFAULT_CREATED_AT, ERR_INVALID_MAX_TIMEOUT),
        (301, DEFAULT_CREATED_AT, ERR_INVOICE_EXPIRY_MISMATCH),
        (300, DEFAULT_CREATED_AT + 61, ERR_INVOICE_CREATED_IN_FUTURE),
    ],
)
def test_invalid_invoice_timing_is_rejected_before_payment(
    max_timeout_seconds: int,
    created_at: int,
    reason: str,
) -> None:
    fixture = build_invoice(created_at=created_at)
    requirements = build_requirements(fixture)
    requirements.max_timeout_seconds = max_timeout_seconds
    payer = FakePayer(paid_status(fixture))

    with pytest.raises(ValueError, match=reason):
        ExactBip122ClientScheme(payer).create_payment_payload(requirements)

    assert payer.calls == []


def test_invoice_at_future_skew_boundary_is_accepted() -> None:
    fixture = build_invoice(created_at=DEFAULT_CREATED_AT + 60)
    payer = FakePayer(paid_status(fixture))

    result = ExactBip122ClientScheme(payer).create_payment_payload(build_requirements(fixture))

    assert result == {"preimage": fixture.preimage}


def test_non_merchant_pay_to_is_rejected_before_payment() -> None:
    fixture = build_invoice()
    requirements = build_requirements(fixture, pay_to="anonymous")
    payer = FakePayer(paid_status(fixture))

    with pytest.raises(ValueError, match=ERR_PAY_TO_MISMATCH):
        ExactBip122ClientScheme(payer).create_payment_payload(requirements)

    assert payer.calls == []


@pytest.mark.parametrize(
    ("status", "reason"),
    [("in_flight", ERR_PAYMENT_IN_FLIGHT), ("unpaid", ERR_PAYMENT_NOT_PAID)],
)
def test_non_paid_status_is_distinct(status: str, reason: str) -> None:
    fixture = build_invoice()
    payer_status = replace(paid_status(fixture), status=status, preimage=None)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=reason):
        ExactBip122ClientScheme(FakePayer(payer_status)).create_payment_payload(
            build_requirements(fixture)
        )


def test_paid_without_preimage_names_adapter_requirement() -> None:
    fixture = build_invoice()
    payer = FakePayer(replace(paid_status(fixture), preimage=None))

    with pytest.raises(ValueError, match=ERR_PAYER_PREIMAGE_REQUIRED) as exc_info:
        ExactBip122ClientScheme(payer).create_payment_payload(build_requirements(fixture))

    assert "payer adapters must expose" in str(exc_info.value)


def test_paid_with_wrong_preimage_is_rejected() -> None:
    fixture = build_invoice()
    payer = FakePayer(replace(paid_status(fixture), preimage="ab" * 32))

    with pytest.raises(ValueError, match=ERR_PAYER_PREIMAGE_HASH_MISMATCH) as exc_info:
        ExactBip122ClientScheme(payer).create_payment_payload(build_requirements(fixture))

    assert "payer adapters must expose" in str(exc_info.value)


def test_paid_with_non_string_preimage_is_adapter_error() -> None:
    fixture = build_invoice()
    payer = FakePayer(replace(paid_status(fixture), preimage=123))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=ERR_PAYER_PREIMAGE_MALFORMED):
        ExactBip122ClientScheme(payer).create_payment_payload(build_requirements(fixture))
