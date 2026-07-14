"""Bitcoin Lightning client implementation for the exact scheme."""

import hashlib
import re
import time
from typing import Any

from ....schemas import PaymentRequirements
from ..constants import (
    ASSET_BTC,
    ERR_INVALID_ASSET,
    ERR_INVOICE_AMOUNT_MISMATCH,
    ERR_INVOICE_CURRENCY_MISMATCH,
    ERR_INVOICE_MISSING,
    ERR_PAY_TO_MISMATCH,
    ERR_PAYER_AMOUNT_MISMATCH,
    ERR_PAYER_INVOICE_MISMATCH,
    ERR_PAYER_PAYMENT_HASH_MISMATCH,
    ERR_PAYER_PREIMAGE_HASH_MISMATCH,
    ERR_PAYER_PREIMAGE_MALFORMED,
    ERR_PAYER_PREIMAGE_REQUIRED,
    ERR_PAYMENT_IN_FLIGHT,
    ERR_PAYMENT_METHOD,
    ERR_PAYMENT_NOT_PAID,
    ERR_UNSUPPORTED_SCHEME,
    PAY_TO_MERCHANT,
    PAYMENT_METHOD_LIGHTNING,
    SCHEME_EXACT,
)
from ..payer import LightningPayer
from ..types import ExactBip122Payload
from ..utils import (
    decode_invoice,
    get_network_config,
    validate_invoice_timing,
    validate_max_timeout_seconds,
    validate_msat_amount,
)


class ExactBip122Scheme:
    """Pay a server-issued BOLT11 invoice and return its preimage."""

    scheme = SCHEME_EXACT

    def __init__(self, payer: LightningPayer) -> None:
        self._payer = payer

    def create_payment_payload(self, requirements: PaymentRequirements) -> dict[str, Any]:
        """Pay the required invoice and construct its cryptographic proof."""
        if requirements.scheme != SCHEME_EXACT:
            raise ValueError(ERR_UNSUPPORTED_SCHEME)

        config = get_network_config(str(requirements.network))
        if requirements.asset != ASSET_BTC:
            raise ValueError(ERR_INVALID_ASSET)
        if requirements.pay_to != PAY_TO_MERCHANT:
            raise ValueError(ERR_PAY_TO_MISMATCH)
        max_timeout_seconds = validate_max_timeout_seconds(requirements.max_timeout_seconds)

        extra = requirements.extra or {}
        if extra.get("paymentMethod") != PAYMENT_METHOD_LIGHTNING:
            raise ValueError(ERR_PAYMENT_METHOD)
        invoice = extra.get("invoice")
        if not isinstance(invoice, str) or not invoice:
            raise ValueError(ERR_INVOICE_MISSING)

        decoded = decode_invoice(invoice)
        if decoded.currency != config["bolt11_currency"]:
            raise ValueError(ERR_INVOICE_CURRENCY_MISMATCH)
        required_amount = validate_msat_amount(requirements.amount)
        if decoded.amount_msat != required_amount:
            raise ValueError(ERR_INVOICE_AMOUNT_MISMATCH)
        validate_invoice_timing(decoded, max_timeout_seconds, time.time())

        status = self._payer.pay_invoice(invoice, str(requirements.network))
        if status.invoice != invoice:
            raise ValueError(ERR_PAYER_INVOICE_MISMATCH)
        if status.payment_hash != decoded.payment_hash:
            raise ValueError(ERR_PAYER_PAYMENT_HASH_MISMATCH)
        if status.amount_msat != required_amount:
            raise ValueError(ERR_PAYER_AMOUNT_MISMATCH)
        if status.status == "in_flight":
            raise ValueError(f"{ERR_PAYMENT_IN_FLIGHT}: payment is still in flight; retry later")
        if status.status != "paid":
            raise ValueError(f"{ERR_PAYMENT_NOT_PAID}: payer reported {status.status}")

        preimage = status.preimage
        adapter_requirement = (
            "payer adapters must expose the 32-byte payment preimage when status is paid"
        )
        if preimage is None or preimage == "":
            raise ValueError(f"{ERR_PAYER_PREIMAGE_REQUIRED}: {adapter_requirement}")
        if not isinstance(preimage, str) or not re.fullmatch(r"[0-9a-f]{64}", preimage):
            raise ValueError(f"{ERR_PAYER_PREIMAGE_MALFORMED}: {adapter_requirement}")
        if hashlib.sha256(bytes.fromhex(preimage)).hexdigest() != decoded.payment_hash:
            raise ValueError(f"{ERR_PAYER_PREIMAGE_HASH_MISMATCH}: {adapter_requirement}")

        return ExactBip122Payload(preimage=preimage).to_dict()
