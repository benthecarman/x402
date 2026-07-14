"""Tests for the exact BIP-122 facilitator scheme."""

import pytest

import x402.mechanisms.bip122.exact.facilitator as facilitator_module
from x402.mechanisms.bip122 import (
    BITCOIN_TESTNET_CAIP2,
    ERR_DUPLICATE_SETTLEMENT,
    ERR_INVALID_ASSET,
    ERR_INVALID_MAX_TIMEOUT,
    ERR_INVOICE_AMOUNT_MISMATCH,
    ERR_INVOICE_CREATED_IN_FUTURE,
    ERR_INVOICE_CURRENCY_MISMATCH,
    ERR_INVOICE_DECODE_FAILED,
    ERR_INVOICE_EXPIRED,
    ERR_INVOICE_EXPIRY_MISMATCH,
    ERR_INVOICE_MISMATCH,
    ERR_INVOICE_MISSING,
    ERR_NETWORK_MISMATCH,
    ERR_PAY_TO_MISMATCH,
    ERR_PAYMENT_METHOD,
    ERR_PREIMAGE_HASH_MISMATCH,
    ERR_PREIMAGE_LENGTH,
    ERR_PREIMAGE_MALFORMED,
    ERR_PREIMAGE_MISSING,
    ERR_UNSUPPORTED_NETWORK,
    ERR_UNSUPPORTED_SCHEME,
    ExactBip122FacilitatorScheme,
    InMemorySettlementStore,
)

from .helpers import build_invoice, build_payload


def assert_reason(scheme, payload, requirements, reason: str) -> None:
    """Assert a stable facilitator invalid reason."""
    result = scheme.verify(payload, requirements)
    assert result.is_valid is False
    assert result.invalid_reason == reason


def test_verify_and_settle_from_preimage_alone() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    scheme = ExactBip122FacilitatorScheme()

    verify = scheme.verify(payload, requirements)
    settle = scheme.settle(payload, requirements)

    assert verify.is_valid is True
    assert verify.payer == "anonymous"
    assert settle.success is True
    assert settle.transaction == fixture.payment_hash
    assert settle.payer == "anonymous"
    assert settle.amount == str(fixture.amount_msat)


@pytest.mark.parametrize("side", ["accepted", "requirements"])
def test_wrong_scheme_is_rejected(side: str) -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    if side == "accepted":
        payload.accepted.scheme = "upto"
    else:
        requirements.scheme = "upto"

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_UNSUPPORTED_SCHEME)


def test_network_mismatch_is_rejected() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    payload.accepted.network = BITCOIN_TESTNET_CAIP2

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_NETWORK_MISMATCH)


def test_unsupported_network_is_rejected() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    payload.accepted.network = requirements.network = "bip122:unknown"

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_UNSUPPORTED_NETWORK)


@pytest.mark.parametrize("side", ["accepted", "requirements"])
def test_non_btc_asset_is_rejected(side: str) -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    if side == "accepted":
        payload.accepted.asset = "USD"
    else:
        requirements.asset = "USD"

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_INVALID_ASSET)


@pytest.mark.parametrize("side", ["accepted", "requirements"])
def test_non_merchant_pay_to_is_rejected(side: str) -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    if side == "accepted":
        payload.accepted.pay_to = "anonymous"
    else:
        requirements.pay_to = "anonymous"

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_PAY_TO_MISMATCH)


@pytest.mark.parametrize("side", ["accepted", "requirements"])
def test_payment_method_mismatch_is_rejected(side: str) -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    target = payload.accepted.extra if side == "accepted" else requirements.extra
    target["paymentMethod"] = "onchain"

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_PAYMENT_METHOD)


@pytest.mark.parametrize("location", ["accepted", "requirements"])
def test_each_invoice_copy_is_required(location: str) -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    if location == "accepted":
        payload.accepted.extra.pop("invoice")
    else:
        requirements.extra.pop("invoice")

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_INVOICE_MISSING)


@pytest.mark.parametrize("location", ["accepted", "requirements"])
def test_invoice_match_blocks_substitution(location: str) -> None:
    fixture = build_invoice()
    other = build_invoice(preimage="ab" * 32)
    payload, requirements = build_payload(fixture)
    if location == "accepted":
        payload.accepted.extra["invoice"] = other.invoice
    else:
        requirements.extra["invoice"] = other.invoice

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_INVOICE_MISMATCH)


def test_invalid_bolt11_is_rejected() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    payload.accepted.extra["invoice"] = "not-a-bolt11"
    requirements.extra["invoice"] = "not-a-bolt11"

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_INVOICE_DECODE_FAILED)


def test_invoice_currency_mismatch_is_rejected() -> None:
    fixture = build_invoice(currency="tb")
    payload, requirements = build_payload(fixture)

    assert_reason(
        ExactBip122FacilitatorScheme(),
        payload,
        requirements,
        ERR_INVOICE_CURRENCY_MISMATCH,
    )


def test_invoice_amount_mismatch_is_rejected() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    requirements.amount = str(fixture.amount_msat + 1)

    assert_reason(
        ExactBip122FacilitatorScheme(), payload, requirements, ERR_INVOICE_AMOUNT_MISMATCH
    )


def test_non_positive_timeout_is_rejected() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    requirements.max_timeout_seconds = 0

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_INVALID_MAX_TIMEOUT)


def test_invoice_expiry_mismatch_is_rejected() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    requirements.max_timeout_seconds += 1

    assert_reason(
        ExactBip122FacilitatorScheme(),
        payload,
        requirements,
        ERR_INVOICE_EXPIRY_MISMATCH,
    )


@pytest.mark.parametrize(
    ("created_at", "valid"),
    [(1_060, True), (1_061, False)],
)
def test_future_invoice_skew_boundary(monkeypatch, created_at: int, valid: bool) -> None:
    fixture = build_invoice(created_at=created_at, expiry_seconds=300)
    payload, requirements = build_payload(fixture)
    monkeypatch.setattr(facilitator_module.time, "time", lambda: 1_000)

    result = ExactBip122FacilitatorScheme().verify(payload, requirements)

    assert result.is_valid is valid
    if not valid:
        assert result.invalid_reason == ERR_INVOICE_CREATED_IN_FUTURE


def test_premarked_payment_hash_is_rejected_as_duplicate() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    store = InMemorySettlementStore()
    assert store.mark_used(fixture.payment_hash, 3600)

    assert_reason(
        ExactBip122FacilitatorScheme(settlement_store=store),
        payload,
        requirements,
        ERR_DUPLICATE_SETTLEMENT,
    )


@pytest.mark.parametrize(
    ("preimage", "reason"),
    [
        (None, ERR_PREIMAGE_MISSING),
        ("GG" * 32, ERR_PREIMAGE_MALFORMED),
        ("aa" * 31, ERR_PREIMAGE_LENGTH),
        ("ab" * 32, ERR_PREIMAGE_HASH_MISMATCH),
    ],
)
def test_preimage_failures_have_distinct_reasons(preimage: str | None, reason: str) -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    if preimage is None:
        payload.payload.pop("preimage")
    else:
        payload.payload["preimage"] = preimage

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, reason)


def test_paid_before_expiry_verified_after_expiry_is_accepted(monkeypatch) -> None:
    fixture = build_invoice(created_at=1_000, expiry_seconds=100)
    payload, requirements = build_payload(fixture)
    monkeypatch.setattr(facilitator_module.time, "time", lambda: 1_101)

    result = ExactBip122FacilitatorScheme().verify(payload, requirements)

    assert result.is_valid is True


def test_verification_after_expiry_window_is_rejected(monkeypatch) -> None:
    fixture = build_invoice(created_at=1_000, expiry_seconds=100)
    payload, requirements = build_payload(fixture)
    monkeypatch.setattr(facilitator_module.time, "time", lambda: 1_161)

    assert_reason(
        ExactBip122FacilitatorScheme(),
        payload,
        requirements,
        ERR_INVOICE_EXPIRED,
    )


def test_expired_without_preimage_is_rejected(monkeypatch) -> None:
    fixture = build_invoice(created_at=1_000, expiry_seconds=100)
    payload, requirements = build_payload(fixture)
    payload.payload.pop("preimage")
    monkeypatch.setattr(facilitator_module.time, "time", lambda: 1_200)

    assert_reason(ExactBip122FacilitatorScheme(), payload, requirements, ERR_PREIMAGE_MISSING)


@pytest.mark.parametrize(("now", "valid"), [(1_160, True), (1_160.001, False)])
def test_skew_boundary(monkeypatch, now: float, valid: bool) -> None:
    fixture = build_invoice(created_at=1_000, expiry_seconds=100)
    payload, requirements = build_payload(fixture)
    monkeypatch.setattr(facilitator_module.time, "time", lambda: now)

    result = ExactBip122FacilitatorScheme().verify(payload, requirements)

    assert result.is_valid is valid
    if not valid:
        assert result.invalid_reason == ERR_INVOICE_EXPIRED


def test_duplicate_settlement_is_rejected() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)
    scheme = ExactBip122FacilitatorScheme()

    assert scheme.settle(payload, requirements).success is True
    second = scheme.settle(payload, requirements)

    assert second.success is False
    assert second.error_reason == ERR_DUPLICATE_SETTLEMENT


class RecordingStore:
    """Custom atomic store that records the requested TTL."""

    def __init__(self, mark_result: bool = True) -> None:
        self.mark_result = mark_result
        self.mark_calls: list[tuple[str, int]] = []

    def is_used(self, payment_hash: str) -> bool:
        _ = payment_hash
        return False

    def mark_used(self, payment_hash: str, ttl_seconds: int) -> bool:
        self.mark_calls.append((payment_hash, ttl_seconds))
        return self.mark_result


def test_custom_store_is_honored_with_one_hour_buffer(monkeypatch) -> None:
    fixture = build_invoice(created_at=1_000, expiry_seconds=300)
    payload, requirements = build_payload(fixture)
    store = RecordingStore()
    monkeypatch.setattr(facilitator_module.time, "time", lambda: 1_001)

    result = ExactBip122FacilitatorScheme(settlement_store=store).settle(payload, requirements)

    assert result.success is True
    assert store.mark_calls == [(fixture.payment_hash, 3_959)]


def test_atomic_store_failure_is_duplicate_settlement() -> None:
    fixture = build_invoice()
    payload, requirements = build_payload(fixture)

    result = ExactBip122FacilitatorScheme(
        settlement_store=RecordingStore(mark_result=False)
    ).settle(payload, requirements)

    assert result.success is False
    assert result.error_reason == ERR_DUPLICATE_SETTLEMENT
