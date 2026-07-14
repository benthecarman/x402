"""Tests for BIP-122 exports and builder registration."""

from x402 import x402ClientSync, x402FacilitatorSync, x402ResourceServerSync
from x402.mechanisms.bip122 import (
    BIP122_CAIP_FAMILY,
    BITCOIN_MAINNET_CAIP2,
    BITCOIN_TESTNET_CAIP2,
    PAY_TO_MERCHANT,
    ExactBip122ClientScheme,
    ExactBip122FacilitatorScheme,
    ExactBip122Payload,
    ExactBip122ServerScheme,
    InMemorySettlementStore,
    LightningInvoiceStatus,
    LightningPayer,
    LightningReceiver,
    SettlementStore,
)

from .fakes import FakePayer, FakeReceiver
from .helpers import build_invoice


def test_public_types_are_exported() -> None:
    assert PAY_TO_MERCHANT == "merchant"
    assert ExactBip122ClientScheme is not None
    assert ExactBip122ServerScheme is not None
    assert ExactBip122FacilitatorScheme is not None
    assert ExactBip122Payload is not None
    assert LightningInvoiceStatus is not None
    assert LightningPayer is not None
    assert LightningReceiver is not None
    assert SettlementStore is not None
    assert InMemorySettlementStore is not None


def test_client_and_server_register_with_family_wildcard() -> None:
    fixture = build_invoice()
    status = LightningInvoiceStatus(
        invoice=fixture.invoice,
        payment_hash=fixture.payment_hash,
        amount_msat=fixture.amount_msat,
        status="paid",
        preimage=fixture.preimage,
    )
    client = x402ClientSync()
    client.register(BIP122_CAIP_FAMILY, ExactBip122ClientScheme(FakePayer(status)))
    server = x402ResourceServerSync()
    server.register(
        BIP122_CAIP_FAMILY,
        ExactBip122ServerScheme(FakeReceiver(fixture.invoice)),
    )

    assert client.get_registered_schemes()[2] == [
        {"network": BIP122_CAIP_FAMILY, "scheme": "exact"}
    ]
    assert server.has_registered_scheme(BITCOIN_MAINNET_CAIP2, "exact")


def test_facilitator_registers_supported_networks() -> None:
    facilitator = x402FacilitatorSync()
    facilitator.register(
        [BITCOIN_MAINNET_CAIP2, BITCOIN_TESTNET_CAIP2],
        ExactBip122FacilitatorScheme(),
    )

    supported = facilitator.get_supported()
    assert {kind.network for kind in supported.kinds} == {
        BITCOIN_MAINNET_CAIP2,
        BITCOIN_TESTNET_CAIP2,
    }


def test_facilitator_accepts_an_explicit_network() -> None:
    facilitator = x402FacilitatorSync()
    facilitator.register(
        [BITCOIN_TESTNET_CAIP2],
        ExactBip122FacilitatorScheme(),
    )

    assert [kind.network for kind in facilitator.get_supported().kinds] == [BITCOIN_TESTNET_CAIP2]
