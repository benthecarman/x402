"""Offline core roundtrips for the Bitcoin Lightning mechanism."""

import pytest

from x402 import (
    x402Client,
    x402ClientSync,
    x402Facilitator,
    x402FacilitatorSync,
    x402ResourceServer,
    x402ResourceServerSync,
)
from x402.mechanisms.bip122 import (
    ASSET_BTC,
    BIP122_CAIP_FAMILY,
    BITCOIN_MAINNET_CAIP2,
    ExactBip122ClientScheme,
    ExactBip122FacilitatorScheme,
    ExactBip122ServerScheme,
    decode_invoice,
)
from x402.schemas import PaymentPayload, PaymentRequirements, ResourceConfig

from .fakes import InMemoryLightningNode


class SyncFacilitatorClient:
    """Adapt an in-process sync facilitator to the resource server protocol."""

    def __init__(self, facilitator: x402FacilitatorSync) -> None:
        self.facilitator = facilitator

    def get_supported(self):
        return self.facilitator.get_supported()

    def verify(self, payload: PaymentPayload, requirements: PaymentRequirements):
        return self.facilitator.verify(payload, requirements)

    def settle(self, payload: PaymentPayload, requirements: PaymentRequirements):
        return self.facilitator.settle(payload, requirements)


class AsyncFacilitatorClient:
    """Adapt an in-process async facilitator to the resource server protocol."""

    def __init__(self, facilitator: x402Facilitator) -> None:
        self.facilitator = facilitator

    def get_supported(self):
        return self.facilitator.get_supported()

    async def verify(self, payload: PaymentPayload, requirements: PaymentRequirements):
        return await self.facilitator.verify(payload, requirements)

    async def settle(self, payload: PaymentPayload, requirements: PaymentRequirements):
        return await self.facilitator.settle(payload, requirements)


def assert_wire_fields(payload: PaymentPayload, requirements: PaymentRequirements) -> None:
    """Assert the Lightning wire contract end to end."""
    invoice = requirements.extra["invoice"]
    assert requirements.scheme == "exact"
    assert requirements.network == BITCOIN_MAINNET_CAIP2
    assert requirements.amount == "21000"
    assert requirements.asset == ASSET_BTC
    assert requirements.pay_to == "merchant"
    assert requirements.extra["paymentMethod"] == "lightning"
    assert isinstance(invoice, str)
    assert payload.accepted.extra["invoice"] == invoice
    assert "invoice" not in payload.payload
    assert len(payload.payload["preimage"]) == 64


def test_full_sync_roundtrip() -> None:
    node = InMemoryLightningNode()
    facilitator = x402FacilitatorSync()
    facilitator.register([BITCOIN_MAINNET_CAIP2], ExactBip122FacilitatorScheme())
    server = x402ResourceServerSync(SyncFacilitatorClient(facilitator))
    server.register(BIP122_CAIP_FAMILY, ExactBip122ServerScheme(node))
    server.initialize()
    client = x402ClientSync()
    client.register(BIP122_CAIP_FAMILY, ExactBip122ClientScheme(node))

    requirements = server.build_payment_requirements(
        ResourceConfig(
            scheme="exact",
            pay_to="",
            price="21 sats",
            network=BITCOIN_MAINNET_CAIP2,
            max_timeout_seconds=300,
        )
    )[0]
    payment_required = server.create_payment_required_response([requirements])
    payload = client.create_payment_payload(payment_required)

    assert_wire_fields(payload, requirements)
    assert server.verify_payment(payload, requirements).is_valid is True
    settled = server.settle_payment(payload, requirements)
    assert settled.success is True
    assert settled.transaction == decode_invoice(requirements.extra["invoice"]).payment_hash
    assert settled.payer == "anonymous"


@pytest.mark.asyncio
async def test_full_async_roundtrip() -> None:
    node = InMemoryLightningNode()
    facilitator = x402Facilitator()
    facilitator.register([BITCOIN_MAINNET_CAIP2], ExactBip122FacilitatorScheme())
    server = x402ResourceServer(AsyncFacilitatorClient(facilitator))
    server.register(BIP122_CAIP_FAMILY, ExactBip122ServerScheme(node))
    server.initialize()
    client = x402Client()
    client.register(BIP122_CAIP_FAMILY, ExactBip122ClientScheme(node))

    requirements = server.build_payment_requirements(
        ResourceConfig(
            scheme="exact",
            pay_to="",
            price="21 sats",
            network=BITCOIN_MAINNET_CAIP2,
            max_timeout_seconds=300,
        )
    )[0]
    payment_required = await server.create_payment_required_response([requirements])
    payload = await client.create_payment_payload(payment_required)

    assert_wire_fields(payload, requirements)
    assert (await server.verify_payment(payload, requirements)).is_valid is True
    settled = await server.settle_payment(payload, requirements)
    assert settled.success is True
    assert settled.transaction == decode_invoice(requirements.extra["invoice"]).payment_hash
    assert settled.payer == "anonymous"
