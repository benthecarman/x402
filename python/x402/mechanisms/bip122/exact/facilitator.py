"""Bitcoin Lightning facilitator implementation for the exact scheme."""

import hashlib
import math
import re
import time
from dataclasses import dataclass
from typing import Any

from ....interfaces import FacilitatorContext
from ....schemas import (
    Network,
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)
from ..constants import (
    ANONYMOUS_PAYER,
    ASSET_BTC,
    BIP122_CAIP_FAMILY,
    DEFAULT_CLOCK_SKEW_SECONDS,
    ERR_DUPLICATE_SETTLEMENT,
    ERR_INVALID_ASSET,
    ERR_INVALID_MAX_TIMEOUT,
    ERR_INVOICE_AMOUNT_MISMATCH,
    ERR_INVOICE_CURRENCY_MISMATCH,
    ERR_INVOICE_DECODE_FAILED,
    ERR_INVOICE_EXPIRED,
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
    MIN_SETTLEMENT_STORE_BUFFER_SECONDS,
    NETWORK_CONFIGS,
    PAY_TO_MERCHANT,
    PAYMENT_METHOD_LIGHTNING,
    SCHEME_EXACT,
)
from ..settlement_store import InMemorySettlementStore, SettlementStore
from ..utils import (
    DecodedInvoice,
    decode_invoice,
    validate_invoice_timing,
    validate_max_timeout_seconds,
    validate_msat_amount,
)


@dataclass(frozen=True)
class _Verification:
    response: VerifyResponse
    invoice: DecodedInvoice | None = None


class ExactBip122Scheme:
    """Verify Lightning payments cryptographically and prevent replay."""

    scheme = SCHEME_EXACT
    caip_family = BIP122_CAIP_FAMILY

    def __init__(
        self,
        settlement_store: SettlementStore | None = None,
        clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    ) -> None:
        if clock_skew_seconds < 0:
            raise ValueError("clock_skew_seconds cannot be negative")
        self._settlement_store = (
            settlement_store if settlement_store is not None else InMemorySettlementStore()
        )
        self._clock_skew_seconds = clock_skew_seconds

    def get_extra(self, network: Network) -> dict[str, Any] | None:
        """Return no facilitator-specific requirement data."""
        _ = network
        return None

    def get_signers(self, network: Network) -> list[str]:
        """Return no signers because facilitators do not receive Lightning funds."""
        _ = network
        return []

    def verify(
        self,
        payload: PaymentPayload,
        requirements: PaymentRequirements,
        context: FacilitatorContext | None = None,
    ) -> VerifyResponse:
        """Verify a BOLT11 invoice payment from its mandatory preimage."""
        _ = context
        return self._verify(payload, requirements).response

    def settle(
        self,
        payload: PaymentPayload,
        requirements: PaymentRequirements,
        context: FacilitatorContext | None = None,
    ) -> SettleResponse:
        """Re-verify and atomically consume the invoice payment hash."""
        _ = context
        verification = self._verify(payload, requirements)
        response = verification.response
        network = str(requirements.network)
        if not response.is_valid or verification.invoice is None:
            return SettleResponse(
                success=False,
                error_reason=response.invalid_reason,
                error_message=response.invalid_message,
                payer=response.payer,
                transaction="",
                network=network,
            )

        invoice = verification.invoice
        now = time.time()
        valid_until = invoice.created_at + invoice.expiry_seconds + self._clock_skew_seconds
        ttl_seconds = math.ceil(
            max(
                MIN_SETTLEMENT_STORE_BUFFER_SECONDS,
                valid_until - now + MIN_SETTLEMENT_STORE_BUFFER_SECONDS,
            )
        )
        if not self._settlement_store.mark_used(invoice.payment_hash, ttl_seconds):
            return SettleResponse(
                success=False,
                error_reason=ERR_DUPLICATE_SETTLEMENT,
                payer=response.payer,
                transaction="",
                network=network,
            )

        return SettleResponse(
            success=True,
            payer=response.payer or ANONYMOUS_PAYER,
            transaction=invoice.payment_hash,
            network=network,
            amount=requirements.amount,
        )

    def _verify(
        self,
        payload: PaymentPayload,
        requirements: PaymentRequirements,
    ) -> _Verification:
        accepted = payload.accepted
        if accepted.scheme != SCHEME_EXACT or requirements.scheme != SCHEME_EXACT:
            return self._invalid(ERR_UNSUPPORTED_SCHEME)
        if str(accepted.network) != str(requirements.network):
            return self._invalid(ERR_NETWORK_MISMATCH)

        network = str(requirements.network)
        config = NETWORK_CONFIGS.get(network)
        if config is None:
            return self._invalid(ERR_UNSUPPORTED_NETWORK)
        if accepted.asset != ASSET_BTC or requirements.asset != ASSET_BTC:
            return self._invalid(ERR_INVALID_ASSET)
        if accepted.pay_to != PAY_TO_MERCHANT or requirements.pay_to != PAY_TO_MERCHANT:
            return self._invalid(ERR_PAY_TO_MISMATCH)
        try:
            max_timeout_seconds = validate_max_timeout_seconds(requirements.max_timeout_seconds)
        except ValueError:
            return self._invalid(ERR_INVALID_MAX_TIMEOUT)

        accepted_extra = accepted.extra or {}
        requirements_extra = requirements.extra or {}
        if (
            accepted_extra.get("paymentMethod") != PAYMENT_METHOD_LIGHTNING
            or requirements_extra.get("paymentMethod") != PAYMENT_METHOD_LIGHTNING
        ):
            return self._invalid(ERR_PAYMENT_METHOD)

        requirements_invoice = requirements_extra.get("invoice")
        accepted_invoice = accepted_extra.get("invoice")
        invoices = (requirements_invoice, accepted_invoice)
        if any(not isinstance(invoice, str) or not invoice for invoice in invoices):
            return self._invalid(ERR_INVOICE_MISSING)
        if requirements_invoice != accepted_invoice:
            return self._invalid(ERR_INVOICE_MISMATCH)
        assert isinstance(requirements_invoice, str)

        try:
            invoice = decode_invoice(requirements_invoice)
        except ValueError as exc:
            return self._invalid(ERR_INVOICE_DECODE_FAILED, message=str(exc))
        if invoice.currency != config["bolt11_currency"]:
            return self._invalid(ERR_INVOICE_CURRENCY_MISMATCH, invoice=invoice)
        try:
            required_amount = validate_msat_amount(requirements.amount)
        except ValueError:
            return self._invalid(ERR_INVOICE_AMOUNT_MISMATCH, invoice=invoice)
        if invoice.amount_msat != required_amount:
            return self._invalid(ERR_INVOICE_AMOUNT_MISMATCH, invoice=invoice)

        now = time.time()
        try:
            validate_invoice_timing(
                invoice,
                max_timeout_seconds,
                now,
                self._clock_skew_seconds,
            )
        except ValueError as exc:
            return self._invalid(str(exc), invoice=invoice)

        if self._settlement_store.is_used(invoice.payment_hash):
            return self._invalid(ERR_DUPLICATE_SETTLEMENT, invoice=invoice)

        preimage = payload.payload.get("preimage")
        if preimage is None or preimage == "":
            return self._invalid(ERR_PREIMAGE_MISSING, invoice=invoice)
        if not isinstance(preimage, str) or re.search(r"[^0-9a-f]", preimage):
            return self._invalid(ERR_PREIMAGE_MALFORMED, invoice=invoice)
        if len(preimage) != 64:
            return self._invalid(ERR_PREIMAGE_LENGTH, invoice=invoice)
        if hashlib.sha256(bytes.fromhex(preimage)).hexdigest() != invoice.payment_hash:
            return self._invalid(ERR_PREIMAGE_HASH_MISMATCH, invoice=invoice)

        invoice_end = invoice.created_at + invoice.expiry_seconds
        if now > invoice_end + self._clock_skew_seconds:
            return self._invalid(
                ERR_INVOICE_EXPIRED,
                invoice=invoice,
            )

        return _Verification(
            response=VerifyResponse(is_valid=True, payer=ANONYMOUS_PAYER),
            invoice=invoice,
        )

    @staticmethod
    def _invalid(
        reason: str,
        invoice: DecodedInvoice | None = None,
        message: str | None = None,
    ) -> _Verification:
        return _Verification(
            response=VerifyResponse(
                is_valid=False,
                invalid_reason=reason,
                invalid_message=message,
                payer=ANONYMOUS_PAYER,
            ),
            invoice=invoice,
        )
