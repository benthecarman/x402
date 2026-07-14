"""Bitcoin Lightning server implementation for the exact scheme."""

import time
from collections.abc import Callable
from decimal import Decimal

from ....schemas import AssetAmount, Network, PaymentRequirements, Price, SupportedKind
from ..constants import (
    ASSET_BTC,
    DEFAULT_INVOICE_MEMO,
    ERR_INVOICE_AMOUNT_MISMATCH,
    ERR_INVOICE_CURRENCY_MISMATCH,
    ERR_INVOICE_ISSUANCE_DENIED,
    PAY_TO_MERCHANT,
    PAYMENT_METHOD_LIGHTNING,
    SCHEME_EXACT,
)
from ..receiver import LightningReceiver
from ..utils import (
    decode_invoice,
    get_network_config,
    parse_money_decimal,
    sat_to_msat,
    validate_invoice_timing,
    validate_max_timeout_seconds,
    validate_msat_amount,
)

MoneyParser = Callable[[Decimal, str], AssetAmount | None]
InvoiceIssuanceLimiter = Callable[[PaymentRequirements], bool]


class ExactBip122Scheme:
    """Issue exact-amount BOLT11 invoices for payment challenges."""

    scheme = SCHEME_EXACT

    def __init__(
        self,
        receiver: LightningReceiver,
        issuance_limiter: InvoiceIssuanceLimiter | None = None,
    ) -> None:
        self._receiver = receiver
        self._issuance_limiter = issuance_limiter
        self._money_parsers: list[MoneyParser] = []

    def register_money_parser(self, parser: MoneyParser) -> "ExactBip122Scheme":
        """Register an exact-decimal price converter, such as a fiat quote source."""
        self._money_parsers.append(parser)
        return self

    def parse_price(self, price: Price, network: Network) -> AssetAmount:
        """Convert a satoshi price or explicit BTC amount to millisatoshis."""
        get_network_config(str(network))

        if isinstance(price, AssetAmount):
            return self._normalize_asset_amount(price)
        if isinstance(price, float):
            raise ValueError("Floating-point prices are not supported; use a decimal string")

        decimal_amount, is_denomination = parse_money_decimal(price)
        for parser in self._money_parsers:
            parsed = parser(decimal_amount, str(network))
            if parsed is not None:
                return self._normalize_asset_amount(parsed)

        if is_denomination:
            raise ValueError(
                "Fiat and BTC-denominated prices are not supported; specify sats or an AssetAmount"
            )

        return AssetAmount(amount=str(sat_to_msat(decimal_amount)), asset=ASSET_BTC)

    def enhance_payment_requirements(
        self,
        requirements: PaymentRequirements,
        supported_kind: SupportedKind,
        extensions: list[str],
    ) -> PaymentRequirements:
        """Create and attach a fresh network-matched BOLT11 invoice."""
        _ = supported_kind, extensions
        config = get_network_config(str(requirements.network))

        requirements.asset = ASSET_BTC
        requirements.pay_to = PAY_TO_MERCHANT
        amount_msat = validate_msat_amount(requirements.amount)
        max_timeout_seconds = validate_max_timeout_seconds(requirements.max_timeout_seconds)

        extra = requirements.extra
        memo_value = extra.pop("description", None)
        memo = memo_value if isinstance(memo_value, str) and memo_value else DEFAULT_INVOICE_MEMO
        extra["paymentMethod"] = PAYMENT_METHOD_LIGHTNING

        if self._issuance_limiter is not None and not self._issuance_limiter(requirements):
            raise ValueError(ERR_INVOICE_ISSUANCE_DENIED)

        invoice = self._receiver.create_invoice(
            amount_msat=amount_msat,
            memo=memo,
            expiry_seconds=max_timeout_seconds,
            network=str(requirements.network),
        )
        decoded = decode_invoice(invoice)
        if decoded.amount_msat != amount_msat:
            raise ValueError(ERR_INVOICE_AMOUNT_MISMATCH)
        if decoded.currency != config["bolt11_currency"]:
            raise ValueError(ERR_INVOICE_CURRENCY_MISMATCH)
        validate_invoice_timing(decoded, max_timeout_seconds, time.time())

        extra["invoice"] = invoice
        return requirements

    @staticmethod
    def _normalize_asset_amount(amount: AssetAmount) -> AssetAmount:
        if amount.asset != ASSET_BTC:
            raise ValueError("Lightning AssetAmount.asset must be BTC")
        validate_msat_amount(amount.amount)
        return amount
