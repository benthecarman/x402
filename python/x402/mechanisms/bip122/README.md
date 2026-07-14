# x402 Bitcoin Lightning Mechanism

Bitcoin Lightning implementation of the x402 `exact` scheme on BIP-122 networks.
The server issues a BOLT11 invoice, the client pays it, and the facilitator verifies
the payment preimage without receiver node access.

## Installation

```bash
uv add "x402[lightning]"
```

## Required Payer Capability

**A payer Lightning node MUST make the 32-byte payment preimage available after a
payment is paid, and the payer adapter MUST return it.** The preimage is the
mandatory proof of payment. A node that does not make it available cannot be used
with this scheme.

The scheme payload contains only the preimage. The server-issued invoice remains
in `PaymentPayload.accepted.extra.invoice`, where the facilitator compares it with
the original payment requirement before verifying the proof.

## Components

- `LightningPayer` pays an invoice and returns `LightningInvoiceStatus`.
- `LightningReceiver` creates fresh invoices.
- `ExactBip122ClientScheme` pays the server-issued invoice.
- `ExactBip122ServerScheme` parses satoshi prices and issues invoices.
- `ExactBip122FacilitatorScheme` verifies preimages and prevents replay.

The facilitator verifies and settles payments from the invoice and mandatory
preimage without access to the receiver node.

## Quick Start

```python
from x402 import x402Client, x402Facilitator, x402ResourceServer
from x402.mechanisms.bip122 import (
    BITCOIN_MAINNET_CAIP2,
    ExactBip122ClientScheme,
    ExactBip122FacilitatorScheme,
    ExactBip122ServerScheme,
)

payer = MyLightningPayer(...)
receiver = MyLightningReceiver(...)

client = x402Client().register(
    "bip122:*",
    ExactBip122ClientScheme(payer),
)

server = x402ResourceServer(facilitator_client).register(
    "bip122:*",
    ExactBip122ServerScheme(receiver),
)

facilitator = x402Facilitator().register(
    [BITCOIN_MAINNET_CAIP2],
    ExactBip122FacilitatorScheme(),
)
```

## Adapter Sketch

Adapters translate Lightning node operations into the mechanism protocols:

```python
from x402.mechanisms.bip122 import LightningInvoiceStatus


class MyLightningPayer:
    def __init__(self, node):
        self.node = node

    def pay_invoice(self, invoice: str, network: str) -> LightningInvoiceStatus:
        result = self.node.pay(invoice, network=network)
        return LightningInvoiceStatus(
            invoice=invoice,
            payment_hash=result.payment_hash,
            amount_msat=result.amount_msat,
            status=result.status,  # "unpaid", "in_flight", or "paid"
            preimage=result.preimage,  # Required when status == "paid".
        )


class MyLightningReceiver:
    def __init__(self, node):
        self.node = node

    def create_invoice(
        self,
        amount_msat: int,
        memo: str,
        expiry_seconds: int,
        network: str,
    ) -> str:
        return self.node.invoice(
            amount_msat=amount_msat,
            memo=memo,
            expiry=expiry_seconds,
            network=network,
        )
```

## Amounts and Recipient Hint

Wire amounts are integer millisatoshi strings. Server prices such as `"21"`,
`"21 sat"`, and `"21 sats"` become `"21000"`. Use `AssetAmount` for an already
atomic value. Floats, negative values, sub-millisatoshi precision, and fiat/BTC
strings are rejected unless a custom exact-decimal money parser is registered.

`payTo` is always the x402 role constant `"merchant"`; the invoice controls
Lightning routing and identifies the actual receiver.

## Invoice Issuance Limiting

Each challenge creates a fresh invoice. Protect unauthenticated routes with the
optional issuance limiter before calling the receiver node:

```python
scheme = ExactBip122ServerScheme(
    receiver,
    issuance_limiter=lambda requirements: rate_limiter.allow(requirements.pay_to),
)
```

Do not reuse an invoice across clients. Reuse breaks attribution and creates
first-payer-wins behavior.

`maxTimeoutSeconds` must be positive, and the receiver must return an invoice with
that exact expiry. Servers, clients, and facilitators also reject invoices dated
more than 60 seconds in the future.

## Settlement Store

`InMemorySettlementStore` is the default and is thread-safe, but it is
**single-process only**. Multi-process or multi-instance facilitators MUST use a
shared store with atomic check-and-set semantics, or one payment can settle once
per instance.

For example, a Redis-backed `mark_used` can use `SET NX EX`:

```python
class RedisSettlementStore:
    def __init__(self, redis):
        self.redis = redis

    def is_used(self, payment_hash: str) -> bool:
        return bool(self.redis.exists(payment_hash))

    def mark_used(self, payment_hash: str, ttl_seconds: int) -> bool:
        return bool(self.redis.set(payment_hash, "1", nx=True, ex=ttl_seconds))
```

The TTL supplied by the scheme covers invoice creation, expiry, clock skew, and at
least one additional hour.

## Exports

### `x402.mechanisms.bip122.exact`

| Export | Description |
|---|---|
| `ExactBip122Scheme` | Alias for the client scheme |
| `ExactBip122ClientScheme` | Pays invoices and builds proofs |
| `ExactBip122ServerScheme` | Parses prices and issues invoices |
| `ExactBip122FacilitatorScheme` | Verifies proofs and consumes payment hashes |
| `MoneyParser` | Custom exact-decimal price parser type |
| `InvoiceIssuanceLimiter` | Invoice issuance policy callable type |

### `x402.mechanisms.bip122`

| Export | Description |
|---|---|
| `LightningPayer` | Payer adapter protocol |
| `LightningReceiver` | Receiver adapter protocol |
| `LightningInvoiceStatus` | Payer invoice result dataclass |
| `SettlementStore` | Atomic replay-store protocol |
| `InMemorySettlementStore` | Single-process TTL store |
| `sat_to_msat()` / `msat_to_sat()` | Exact amount conversion helpers |
| `validate_max_timeout_seconds()` / `validate_invoice_timing()` | Shared invoice timing validators |
| `PAY_TO_MERCHANT` | Fixed `payTo` role constant (`"merchant"`) |
| `NETWORK_CONFIGS` | BIP-122 network-to-BOLT11 configuration |

See the [normative scheme specification](../../../../specs/schemes/exact/scheme_exact_bip122.md)
for the complete wire format, validation order, and error vocabulary.
