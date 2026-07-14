"""Bitcoin Lightning mechanism constants."""

from typing import TypedDict

SCHEME_EXACT = "exact"
ASSET_BTC = "BTC"
PAYMENT_METHOD_LIGHTNING = "lightning"
PAY_TO_MERCHANT = "merchant"
ANONYMOUS_PAYER = "anonymous"
BIP122_CAIP_FAMILY = "bip122:*"

BITCOIN_MAINNET_CAIP2 = "bip122:000000000019d6689c085ae165831e93"
BITCOIN_TESTNET_CAIP2 = "bip122:000000000933ea01ad0ee984209779ba"

DEFAULT_CLOCK_SKEW_SECONDS = 60
MIN_SETTLEMENT_STORE_BUFFER_SECONDS = 3600
DEFAULT_INVOICE_MEMO = "x402 payment"


class NetworkConfig(TypedDict):
    """Configuration for a BIP-122 Lightning network."""

    bolt11_currency: str


NETWORK_CONFIGS: dict[str, NetworkConfig] = {
    BITCOIN_MAINNET_CAIP2: {"bolt11_currency": "bc"},
    BITCOIN_TESTNET_CAIP2: {"bolt11_currency": "tb"},
}
SUPPORTED_NETWORKS = tuple(NETWORK_CONFIGS)

# Facilitator invalidReason/errorReason values.
ERR_UNSUPPORTED_SCHEME = "unsupported_scheme"
ERR_NETWORK_MISMATCH = "network_mismatch"
ERR_UNSUPPORTED_NETWORK = "unsupported_network"
ERR_INVALID_ASSET = "invalid_exact_bip122_asset"
ERR_PAY_TO_MISMATCH = "invalid_exact_bip122_pay_to_mismatch"
ERR_PAYMENT_METHOD = "invalid_exact_bip122_payment_method"
ERR_INVOICE_MISSING = "invalid_exact_bip122_invoice_missing"
ERR_INVOICE_MISMATCH = "invalid_exact_bip122_invoice_mismatch"
ERR_INVOICE_DECODE_FAILED = "invalid_exact_bip122_invoice_decode_failed"
ERR_INVOICE_CURRENCY_MISMATCH = "invalid_exact_bip122_invoice_currency_mismatch"
ERR_INVOICE_AMOUNT_MISMATCH = "invalid_exact_bip122_invoice_amount_mismatch"
ERR_INVALID_MAX_TIMEOUT = "invalid_exact_bip122_max_timeout"
ERR_INVOICE_EXPIRY_MISMATCH = "invalid_exact_bip122_invoice_expiry_mismatch"
ERR_INVOICE_CREATED_IN_FUTURE = "invalid_exact_bip122_invoice_created_in_future"
ERR_DUPLICATE_SETTLEMENT = "duplicate_settlement"
ERR_PREIMAGE_MISSING = "invalid_exact_bip122_preimage_missing"
ERR_PREIMAGE_MALFORMED = "invalid_exact_bip122_preimage_malformed"
ERR_PREIMAGE_LENGTH = "invalid_exact_bip122_preimage_length"
ERR_PREIMAGE_HASH_MISMATCH = "invalid_exact_bip122_preimage_hash_mismatch"
ERR_INVOICE_EXPIRED = "invalid_exact_bip122_invoice_expired"

# Local client/server diagnostics.
ERR_INVOICE_ISSUANCE_DENIED = "exact_bip122_invoice_issuance_denied"
ERR_PAYER_INVOICE_MISMATCH = "invalid_exact_bip122_payer_invoice_mismatch"
ERR_PAYER_PAYMENT_HASH_MISMATCH = "invalid_exact_bip122_payer_payment_hash_mismatch"
ERR_PAYER_AMOUNT_MISMATCH = "invalid_exact_bip122_payer_amount_mismatch"
ERR_PAYMENT_IN_FLIGHT = "exact_bip122_payment_in_flight"
ERR_PAYMENT_NOT_PAID = "exact_bip122_payment_not_paid"
ERR_PAYER_PREIMAGE_REQUIRED = "invalid_exact_bip122_payer_preimage_required"
ERR_PAYER_PREIMAGE_MALFORMED = "invalid_exact_bip122_payer_preimage_malformed"
ERR_PAYER_PREIMAGE_HASH_MISMATCH = "invalid_exact_bip122_payer_preimage_hash_mismatch"
