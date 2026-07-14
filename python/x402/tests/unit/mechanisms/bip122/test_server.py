"""Tests for the exact BIP-122 server scheme."""

from decimal import Decimal

import pytest

from x402.mechanisms.bip122 import (
    ASSET_BTC,
    BITCOIN_MAINNET_CAIP2,
    ERR_INVALID_MAX_TIMEOUT,
    ERR_INVOICE_AMOUNT_MISMATCH,
    ERR_INVOICE_CREATED_IN_FUTURE,
    ERR_INVOICE_CURRENCY_MISMATCH,
    ERR_INVOICE_EXPIRY_MISMATCH,
    ERR_INVOICE_ISSUANCE_DENIED,
    PAY_TO_MERCHANT,
    ExactBip122ServerScheme,
)
from x402.schemas import AssetAmount, PaymentRequirements, SupportedKind

from .fakes import FakeReceiver
from .helpers import DEFAULT_CREATED_AT, build_invoice, build_requirements


def supported_kind() -> SupportedKind:
    """Return the facilitator kind used during requirement enhancement."""
    return SupportedKind(
        x402_version=2,
        scheme="exact",
        network=BITCOIN_MAINNET_CAIP2,
    )


def test_enhance_payment_requirements_issues_fresh_invoice() -> None:
    fixture = build_invoice(amount_msat=21_000, expiry_seconds=120)
    receiver = FakeReceiver(fixture.invoice)
    requirements = build_requirements(fixture)
    requirements.asset = ""
    requirements.extra = {"description": "weather data"}

    result = ExactBip122ServerScheme(receiver).enhance_payment_requirements(
        requirements, supported_kind(), []
    )

    assert result.asset == ASSET_BTC
    assert result.extra == {
        "paymentMethod": "lightning",
        "invoice": fixture.invoice,
    }
    assert receiver.create_calls == [(21_000, "weather data", 120, BITCOIN_MAINNET_CAIP2)]


def test_receiver_amount_mismatch_is_rejected() -> None:
    required = build_invoice(amount_msat=21_000)
    wrong = build_invoice(amount_msat=22_000)

    with pytest.raises(ValueError, match=ERR_INVOICE_AMOUNT_MISMATCH):
        ExactBip122ServerScheme(FakeReceiver(wrong.invoice)).enhance_payment_requirements(
            build_requirements(required), supported_kind(), []
        )


def test_receiver_currency_mismatch_is_rejected() -> None:
    fixture = build_invoice(currency="tb")

    with pytest.raises(ValueError, match=ERR_INVOICE_CURRENCY_MISMATCH):
        ExactBip122ServerScheme(FakeReceiver(fixture.invoice)).enhance_payment_requirements(
            build_requirements(fixture), supported_kind(), []
        )


def test_non_positive_timeout_is_rejected_before_invoice_issuance() -> None:
    fixture = build_invoice()
    receiver = FakeReceiver(fixture.invoice)
    requirements = build_requirements(fixture)
    requirements.max_timeout_seconds = 0

    with pytest.raises(ValueError, match=ERR_INVALID_MAX_TIMEOUT):
        ExactBip122ServerScheme(receiver).enhance_payment_requirements(
            requirements, supported_kind(), []
        )

    assert receiver.create_calls == []


def test_receiver_expiry_mismatch_is_rejected() -> None:
    required = build_invoice(expiry_seconds=300)
    wrong = build_invoice(expiry_seconds=301)

    with pytest.raises(ValueError, match=ERR_INVOICE_EXPIRY_MISMATCH):
        ExactBip122ServerScheme(FakeReceiver(wrong.invoice)).enhance_payment_requirements(
            build_requirements(required), supported_kind(), []
        )


def test_receiver_future_timestamp_is_rejected() -> None:
    fixture = build_invoice(created_at=DEFAULT_CREATED_AT + 61)

    with pytest.raises(ValueError, match=ERR_INVOICE_CREATED_IN_FUTURE):
        ExactBip122ServerScheme(FakeReceiver(fixture.invoice)).enhance_payment_requirements(
            build_requirements(fixture), supported_kind(), []
        )


def test_receiver_timestamp_at_skew_boundary_is_accepted() -> None:
    fixture = build_invoice(created_at=DEFAULT_CREATED_AT + 60)

    result = ExactBip122ServerScheme(FakeReceiver(fixture.invoice)).enhance_payment_requirements(
        build_requirements(fixture), supported_kind(), []
    )

    assert result.extra["invoice"] == fixture.invoice


@pytest.mark.parametrize("pay_to", ["node-pubkey", "", PAY_TO_MERCHANT])
def test_pay_to_is_fixed_to_merchant_role(pay_to: str) -> None:
    fixture = build_invoice()
    requirements = build_requirements(fixture, pay_to=pay_to)

    result = ExactBip122ServerScheme(FakeReceiver(fixture.invoice)).enhance_payment_requirements(
        requirements, supported_kind(), []
    )

    assert result.pay_to == PAY_TO_MERCHANT


def test_issuance_limiter_denial_prevents_receiver_call() -> None:
    fixture = build_invoice()
    receiver = FakeReceiver(fixture.invoice)
    scheme = ExactBip122ServerScheme(receiver, issuance_limiter=lambda requirements: False)

    with pytest.raises(ValueError, match=ERR_INVOICE_ISSUANCE_DENIED):
        scheme.enhance_payment_requirements(build_requirements(fixture), supported_kind(), [])

    assert receiver.create_calls == []


@pytest.mark.parametrize("price", ["21", "21 sat", "21 sats", 21])
def test_satoshi_money_parsing(price: str | int) -> None:
    scheme = ExactBip122ServerScheme(FakeReceiver(build_invoice().invoice))

    assert scheme.parse_price(price, BITCOIN_MAINNET_CAIP2) == AssetAmount(
        amount="21000", asset=ASSET_BTC
    )


def test_asset_amount_is_already_in_millisatoshis() -> None:
    scheme = ExactBip122ServerScheme(FakeReceiver(build_invoice().invoice))
    price = AssetAmount(amount="21", asset=ASSET_BTC, extra={"reference": "sku-1"})

    assert scheme.parse_price(price, BITCOIN_MAINNET_CAIP2) == price


def test_custom_money_parser_can_convert_fiat() -> None:
    scheme = ExactBip122ServerScheme(FakeReceiver(build_invoice().invoice))
    seen: list[tuple[Decimal, str]] = []

    def parser(amount: Decimal, network: str) -> AssetAmount:
        seen.append((amount, network))
        return AssetAmount(amount="1234", asset=ASSET_BTC)

    scheme.register_money_parser(parser)

    assert scheme.parse_price("$1.25", BITCOIN_MAINNET_CAIP2).amount == "1234"
    assert seen == [(Decimal("1.25"), BITCOIN_MAINNET_CAIP2)]


@pytest.mark.parametrize("price", ["$1", "1 USD", "0.0001 BTC"])
def test_fiat_and_btc_inputs_are_rejected_without_custom_parser(price: str) -> None:
    scheme = ExactBip122ServerScheme(FakeReceiver(build_invoice().invoice))

    with pytest.raises(ValueError, match="specify sats or an AssetAmount"):
        scheme.parse_price(price, BITCOIN_MAINNET_CAIP2)


@pytest.mark.parametrize(
    "price",
    ["0.0001 sat", "-1", AssetAmount(amount="-1", asset=ASSET_BTC)],
)
def test_precision_and_negative_inputs_are_rejected(price) -> None:
    scheme = ExactBip122ServerScheme(FakeReceiver(build_invoice().invoice))

    with pytest.raises(ValueError):
        scheme.parse_price(price, BITCOIN_MAINNET_CAIP2)


def test_enhancement_defaults_memo() -> None:
    fixture = build_invoice()
    receiver = FakeReceiver(fixture.invoice)
    requirements = PaymentRequirements(
        scheme="exact",
        network=BITCOIN_MAINNET_CAIP2,
        amount=str(fixture.amount_msat),
        asset=ASSET_BTC,
        pay_to="seller",
        max_timeout_seconds=300,
    )

    ExactBip122ServerScheme(receiver).enhance_payment_requirements(
        requirements, supported_kind(), []
    )

    assert receiver.create_calls[0][1] == "x402 payment"
