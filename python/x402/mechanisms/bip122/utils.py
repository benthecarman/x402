"""BOLT11 decoding and exact Bitcoin amount utilities."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

try:
    from bolt11 import decode as bolt11_decode
except ImportError as exc:
    raise ImportError(
        "Bitcoin Lightning support requires the bolt11 package. "
        "Install it with: pip install x402[lightning]"
    ) from exc

from .constants import (
    DEFAULT_CLOCK_SKEW_SECONDS,
    ERR_INVALID_MAX_TIMEOUT,
    ERR_INVOICE_CREATED_IN_FUTURE,
    ERR_INVOICE_EXPIRY_MISMATCH,
    NETWORK_CONFIGS,
    NetworkConfig,
)

_SAT_AMOUNT_RE = re.compile(r"^(?P<amount>-?\d+(?:\.\d+)?)\s*(?:sat|sats)?$", re.IGNORECASE)
_DENOMINATED_AMOUNT_RE = re.compile(
    r"^\s*\$?\s*(?P<amount>-?\d+(?:\.\d+)?)\s*(?:usd|btc)?\s*$",
    re.IGNORECASE,
)
_BOLT11_HRP_RE = re.compile(r"^ln(?:bc|tb)(?:(\d+)([munp]?))?1", re.IGNORECASE)
_LOWER_HEX_32_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class DecodedInvoice:
    """Fields required to verify an exact BOLT11 payment."""

    currency: str
    amount_msat: int | None
    payment_hash: str
    created_at: int
    expiry_seconds: int


def get_network_config(network: str) -> NetworkConfig:
    """Return the supported network configuration."""
    config = NETWORK_CONFIGS.get(network)
    if config is None:
        raise ValueError(f"Unsupported BIP-122 network: {network}")
    return config


def sat_to_msat(value: Decimal | int | str) -> int:
    """Convert a non-negative satoshi amount to integral millisatoshis."""
    amount = _parse_sat_amount(value)
    millisatoshis = amount * Decimal(1000)
    if millisatoshis != millisatoshis.to_integral_value():
        raise ValueError("Satoshi amount has sub-millisatoshi precision")
    return int(millisatoshis)


def msat_to_sat(value: Decimal | int | str) -> Decimal:
    """Convert integral millisatoshis to satoshis without floating point."""
    millisatoshis = _parse_non_negative_decimal(value, "millisatoshi")
    if millisatoshis != millisatoshis.to_integral_value():
        raise ValueError("Millisatoshi amount must be an integer")
    return millisatoshis / Decimal(1000)


def parse_money_decimal(value: str | int) -> tuple[Decimal, bool]:
    """Return a decimal price and whether it used a prohibited denomination."""
    if isinstance(value, bool):
        raise ValueError("Boolean prices are not supported")
    if isinstance(value, int):
        return _parse_non_negative_decimal(value, "satoshi"), False

    raw = value.strip()
    is_denomination = "$" in raw or bool(re.search(r"\b(?:usd|btc)\b", raw, re.I))
    if is_denomination:
        match = _DENOMINATED_AMOUNT_RE.fullmatch(raw)
    else:
        match = _SAT_AMOUNT_RE.fullmatch(raw)
    if match is None:
        raise ValueError("Invalid price; specify a satoshi amount such as '21 sats'")
    return _parse_non_negative_decimal(match.group("amount"), "satoshi"), is_denomination


def validate_msat_amount(value: str) -> int:
    """Parse a non-negative integer millisatoshi wire amount."""
    if not re.fullmatch(r"\d+", value):
        raise ValueError("Millisatoshi amount must be a non-negative integer string")
    return int(value)


def validate_max_timeout_seconds(value: int) -> int:
    """Require a positive integral invoice timeout."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(ERR_INVALID_MAX_TIMEOUT)
    return value


def validate_invoice_timing(
    invoice: DecodedInvoice,
    max_timeout_seconds: int,
    now: float,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
) -> None:
    """Bind invoice expiry to x402 timeout and reject future-dated invoices."""
    timeout = validate_max_timeout_seconds(max_timeout_seconds)
    if invoice.expiry_seconds != timeout:
        raise ValueError(ERR_INVOICE_EXPIRY_MISMATCH)
    if invoice.created_at > now + clock_skew_seconds:
        raise ValueError(ERR_INVOICE_CREATED_IN_FUTURE)


def is_lower_hex_32(value: str) -> bool:
    """Return whether ``value`` is exactly 32 bytes of lowercase hex."""
    return bool(_LOWER_HEX_32_RE.fullmatch(value))


def decode_invoice(invoice: str) -> DecodedInvoice:
    """Strictly decode and signature-check a BOLT11 invoice."""
    if not isinstance(invoice, str) or not invoice:
        raise ValueError("BOLT11 invoice is required")
    if invoice != invoice.lower() and invoice != invoice.upper():
        raise ValueError("BOLT11 invoice cannot mix uppercase and lowercase characters")

    hrp_match = _BOLT11_HRP_RE.match(invoice)
    if hrp_match is None:
        raise ValueError("Invalid BOLT11 human-readable part")
    amount_digits, multiplier = hrp_match.groups()
    if multiplier and multiplier.lower() == "p" and int(amount_digits or "") % 10 != 0:
        raise ValueError("BOLT11 amount has sub-millisatoshi precision")

    try:
        decoded = bolt11_decode(invoice, strict=True)
    except Exception as exc:
        raise ValueError("Invalid BOLT11 invoice") from exc

    currency = str(decoded.currency)
    amount_msat = int(decoded.amount_msat) if decoded.amount_msat is not None else None
    payment_hash = str(decoded.payment_hash)
    if not _LOWER_HEX_32_RE.fullmatch(payment_hash):
        raise ValueError("BOLT11 payment hash must be 32 bytes")

    return DecodedInvoice(
        currency=currency,
        amount_msat=amount_msat,
        payment_hash=payment_hash,
        created_at=int(decoded.date),
        expiry_seconds=int(decoded.expiry),
    )


def _parse_sat_amount(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return _parse_non_negative_decimal(value, "satoshi")
    if isinstance(value, int) and not isinstance(value, bool):
        return _parse_non_negative_decimal(value, "satoshi")
    if not isinstance(value, str):
        raise ValueError("Satoshi amount must be a Decimal, integer, or string")
    amount, is_denomination = parse_money_decimal(value)
    if is_denomination:
        raise ValueError(
            "Fiat and BTC-denominated prices are not supported; specify sats or an AssetAmount"
        )
    return amount


def _parse_non_negative_decimal(value: Decimal | int | str, unit: str) -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid {unit} amount: {value}") from exc
    if not amount.is_finite():
        raise ValueError(f"Invalid {unit} amount: {value}")
    if amount < 0:
        raise ValueError(f"{unit.capitalize()} amount cannot be negative")
    return amount
