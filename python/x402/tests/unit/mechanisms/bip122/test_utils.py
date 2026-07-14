"""Tests for BIP-122 amount and invoice utilities."""

from decimal import Decimal

import pytest

from x402.mechanisms.bip122 import (
    BITCOIN_MAINNET_CAIP2,
    BITCOIN_TESTNET_CAIP2,
    NETWORK_CONFIGS,
    decode_invoice,
    msat_to_sat,
    sat_to_msat,
)

from .helpers import build_invoice


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("21", 21_000),
        ("21 sat", 21_000),
        ("21 sats", 21_000),
        (Decimal("0.001"), 1),
    ],
)
def test_sat_to_msat_uses_exact_decimal_arithmetic(value, expected: int) -> None:
    assert sat_to_msat(value) == expected


def test_msat_to_sat_preserves_fractional_satoshis() -> None:
    assert msat_to_sat("21001") == Decimal("21.001")


@pytest.mark.parametrize("value", ["-1", Decimal("-0.001"), "0.0001 sat"])
def test_amount_helpers_reject_negative_or_sub_msat_values(value) -> None:
    with pytest.raises(ValueError):
        sat_to_msat(value)


@pytest.mark.parametrize("value", ["$1", "1 usd", "1 BTC"])
def test_sat_helper_rejects_fiat_looking_values(value: str) -> None:
    with pytest.raises(ValueError, match="specify sats or an AssetAmount"):
        sat_to_msat(value)


def test_decode_invoice_returns_strict_signed_fields() -> None:
    fixture = build_invoice()

    decoded = decode_invoice(fixture.invoice)

    assert decoded.currency == fixture.currency
    assert decoded.amount_msat == fixture.amount_msat
    assert decoded.payment_hash == fixture.payment_hash
    assert decoded.created_at == fixture.created_at
    assert decoded.expiry_seconds == fixture.expiry_seconds


def test_decode_invoice_rejects_mixed_case_bech32() -> None:
    fixture = build_invoice()
    mixed_case = fixture.invoice[0].upper() + fixture.invoice[1:]

    with pytest.raises(ValueError, match="cannot mix uppercase and lowercase"):
        decode_invoice(mixed_case)


def test_network_config_has_required_bolt11_currencies() -> None:
    assert NETWORK_CONFIGS[BITCOIN_MAINNET_CAIP2]["bolt11_currency"] == "bc"
    assert NETWORK_CONFIGS[BITCOIN_TESTNET_CAIP2]["bolt11_currency"] == "tb"
