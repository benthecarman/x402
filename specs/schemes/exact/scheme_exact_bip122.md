# Scheme: `exact` on Bitcoin Lightning (`BIP-122`)

## Summary

This document specifies the x402 `exact` payment scheme for Bitcoin Lightning
networks identified by the CAIP-2 `bip122` namespace. A resource server issues a
fresh BOLT11 invoice, the client pays it, and the client proves payment by returning
the invoice's 32-byte payment preimage.

The preimage is mandatory. A facilitator verifies
`SHA-256(preimage) == payment_hash` from the signed invoice and therefore does not
need access to the receiver's Lightning node. Independent third-party facilitators
work by default. A client MUST use a payer Lightning node that makes the preimage
available after payment; otherwise, the client MUST NOT select this scheme.

This scheme targets x402 protocol version 2 and uses the core
`PaymentRequirements`, `PaymentPayload`, `VerifyResponse`, and `SettleResponse`
types from [x402-specification-v2.md](../../x402-specification-v2.md).

## Scheme and Networks

- `scheme` MUST be `"exact"`.
- `asset` MUST be `"BTC"`.
- Mainnet MUST use
  `bip122:000000000019d6689c085ae165831e93` and BOLT11 currency `bc`.
- Bitcoin testnet MUST use
  `bip122:000000000933ea01ad0ee984209779ba` and BOLT11 currency `tb`.
- Messages on the wire MUST use one of these concrete network identifiers.

## Terminology and Adapter Requirements

- **Receiver**: The seller-side Lightning node that creates invoices.
- **Payer**: The client-side Lightning node that pays an invoice.
- **Payment hash**: The 32-byte value committed to by the BOLT11 invoice.
- **Preimage**: The 32-byte secret whose SHA-256 digest is the payment hash.
- **Replay store**: Atomic storage recording payment hashes already settled by a
  facilitator.

Before selecting this scheme, a client MUST ensure that its payer Lightning node
makes the payment preimage available after a successful payment. A payer adapter
MUST return that preimage when it reports a payment as paid. These are hard
compatibility requirements; a payer Lightning node that does not make the preimage
available cannot be used with this scheme.

A receiver adapter MUST be able to create a fresh invoice for an exact
millisatoshi amount. Facilitators do not require receiver access.

## Amounts

All x402 wire amounts for this scheme MUST be decimal strings containing a
non-negative integer number of millisatoshis. Floating-point values, fractional
millisatoshis, signs, exponent notation, separators, and unit suffixes MUST NOT
appear on the wire. The BOLT11 invoice MUST encode an amount and that amount MUST
be an integral number of millisatoshis.

Examples:

| Meaning | Wire `amount` |
|---|---:|
| 1 millisatoshi | `"1"` |
| 1 satoshi | `"1000"` |
| 21 satoshis | `"21000"` |
| 1 bitcoin | `"100000000000"` |

User-facing SDK price parsers SHOULD accept satoshi inputs such as `"21"`,
`"21 sat"`, and `"21 sats"` and convert them to `"21000"`. They MUST use exact
decimal arithmetic, MUST reject negative values and sub-millisatoshi precision,
and MUST reject fiat- or bitcoin-denominated inputs such as `$1`, `1 USD`, or
`0.0001 BTC` unless an application explicitly registered a conversion parser.
The rejection SHOULD direct callers to specify sats or an explicit atomic
`AssetAmount`.

## `PaymentRequirements`

The resource server MUST generate a fresh BOLT11 invoice for each payment
challenge and place it in `extra.invoice`.

```json
{
  "scheme": "exact",
  "network": "bip122:000000000019d6689c085ae165831e93",
  "amount": "25000",
  "asset": "BTC",
  "payTo": "merchant",
  "maxTimeoutSeconds": 300,
  "extra": {
    "paymentMethod": "lightning",
    "invoice": "lnbc250n1pj48ugqpp54y3u9s8ylemsv8l3ewyzzu0klhujvuvmkl6llchq23vy8rzjsf0qsp5zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zygsdq80q6rqvsxqzfvcqpjpal2l7zmrg46wpsxvv8aly29hzrjhvyxcrxxdm3r4ky8etpthh9p3r2ly8jvtlv6wprwvrm5t2zrxxmvpg57xhf24x2ngrd8smj8jtcp79fu42"
  }
}
```

The Lightning-specific fields are:

| Field | Required | Meaning |
|---|---|---|
| `extra.paymentMethod` | Yes | MUST be `"lightning"`. |
| `extra.invoice` | Yes | Fresh, strictly valid, signed BOLT11 invoice for `amount` on `network`. |

`maxTimeoutSeconds` MUST be a positive integer. The BOLT11 invoice expiry MUST
equal `maxTimeoutSeconds` exactly.

`payTo` MUST be the role constant `"merchant"`. It identifies the receiver's role
without naming a Lightning node or account. It does not control routing; the
invoice controls the destination of funds. Servers MUST set this value, clients
MUST reject any other value, and facilitators MUST require it in both the original
requirement and `PaymentPayload.accepted`.

Before returning the challenge, the server MUST strictly decode the invoice and
verify all of the following:

1. The BOLT11 amount equals `PaymentRequirements.amount` exactly.
2. The BOLT11 currency matches the concrete network (`bc` for mainnet, `tb` for
   testnet).
3. The BOLT11 expiry equals `maxTimeoutSeconds` exactly.
4. The BOLT11 creation time is not later than the server's validation time plus
   its configured non-negative clock-skew allowance, whose default MUST be 60
   seconds. Equality at this boundary is valid.

The server MUST NOT reuse an invoice across clients or challenges.

## `PaymentPayload`

After paying the invoice, the client sends the preimage in the scheme-specific
`payload` object. The invoice remains in `accepted.extra.invoice`:

```json
{
  "x402Version": 2,
  "accepted": {
    "scheme": "exact",
    "network": "bip122:000000000019d6689c085ae165831e93",
    "amount": "25000",
    "asset": "BTC",
    "payTo": "merchant",
    "maxTimeoutSeconds": 300,
    "extra": {
      "paymentMethod": "lightning",
      "invoice": "lnbc250n1pj48ugqpp54y3u9s8ylemsv8l3ewyzzu0klhujvuvmkl6llchq23vy8rzjsf0qsp5zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zygsdq80q6rqvsxqzfvcqpjpal2l7zmrg46wpsxvv8aly29hzrjhvyxcrxxdm3r4ky8etpthh9p3r2ly8jvtlv6wprwvrm5t2zrxxmvpg57xhf24x2ngrd8smj8jtcp79fu42"
    }
  },
  "payload": {
    "preimage": "0001020304050607080900010203040506070809000102030405060708090102"
  }
}
```

The payload field is required:

| Field | Type | Requirements |
|---|---|---|
| `preimage` | string | MUST be exactly 64 lowercase hexadecimal characters encoding 32 bytes. |

`accepted.extra.invoice` MUST be byte-identical to the original
`PaymentRequirements.extra.invoice`. This comparison prevents a client from
replacing the server-issued invoice with a self-issued invoice whose preimage it
already knows.

## Client Payment Construction

Before paying, a client MUST:

1. Require `scheme == "exact"`, a supported concrete network, `asset == "BTC"`,
   `payTo == "merchant"`, a positive integral `maxTimeoutSeconds`,
   `extra.paymentMethod == "lightning"`, and a non-empty `extra.invoice`.
2. Strictly decode and signature-check the BOLT11 invoice.
3. Verify the invoice currency matches the selected network.
4. Verify the invoice has an integral millisatoshi amount equal to
   `PaymentRequirements.amount`.
5. Verify the invoice expiry equals `maxTimeoutSeconds` and its creation time is
   not later than the client's validation time plus its configured non-negative
   clock-skew allowance, whose default MUST be 60 seconds.
6. Ask its payer adapter to pay that exact invoice on that exact network.

The payer result MUST identify the same invoice, payment hash, and amount and MUST
report `paid`. An `in_flight` result SHOULD be surfaced distinctly so the caller can
retry without initiating a second payment. After a paid result, the client MUST
require the preimage, validate its wire format, and verify its SHA-256 digest. The
client MUST NOT construct a `PaymentPayload` if any check fails.

## Facilitator Verification

A facilitator MUST treat the payload and echoed requirements as untrusted. It MUST
perform the following checks in order:

1. Require `exact` on both sides; require matching, supported networks; require
   `BTC` on both sides; require `payTo == "merchant"` on both sides; and require
   `lightning` in both `extra.paymentMethod` fields. Require
   `requirements.maxTimeoutSeconds` to be a positive integer.
2. Require an invoice in `requirements.extra.invoice` and
   `accepted.extra.invoice`, and require the two strings to be byte-identical.
3. Strictly decode and signature-check the invoice. Require the BOLT11 currency to
   match the network and its integral millisatoshi amount to equal
   `requirements.amount` exactly. Require its expiry to equal
   `requirements.maxTimeoutSeconds`, and require its creation time not to exceed
   the facilitator's verification time plus the configured clock-skew allowance.
4. Reject the payment hash if the replay store already marks it used.
5. Require the preimage, require exactly 64 lowercase hexadecimal characters,
   decode exactly 32 bytes, and require
   `SHA-256(preimage_bytes) == payment_hash_bytes`.
6. Apply the expiry policy below.

Possession of a valid preimage proves that the invoice settled: before payment, the
preimage is known only to the receiver. Preimage verification MUST NOT be skipped,
and facilitators MUST NOT require receiver access to verify it.

### Paid-but-expired Policy

An invoice MUST NOT be rejected merely because verification happens after its
BOLT11 expiry time. Let:

- `invoice_end = invoice_creation_time + invoice_expiry_seconds`
- `verification_time =` the facilitator's verification time
- `skew =` the facilitator's configured non-negative clock-skew allowance, whose
  default MUST be 60 seconds

An expired invoice is valid if and only if the preimage verifies and
`verification_time <= invoice_end + skew`. Verification after that boundary MUST
be rejected as expired. Equality at the boundary is valid.

This prevents a client that paid immediately before expiry from losing access only
because its retried resource request arrived just after expiry. Verification time
is the conservative settlement-time proxy.

## Settlement and Replay Protection

Settlement does not move funds; the Lightning payment already settled when the
preimage became available. The facilitator MUST re-run all verification checks and
then atomically mark the invoice payment hash used. The atomic operation MUST fail
if the key already exists. A failed atomic mark MUST return `duplicate_settlement`.

The replay entry TTL MUST extend through the invoice's creation time, expiry,
clock-skew allowance, and an additional buffer of at least one hour. An entry MUST
never be pruned while the invoice could still pass verification.

On success, `SettleResponse.transaction` MUST be the lowercase invoice payment hash,
`network` MUST be the concrete BIP-122 network, and `payer` MUST be `"anonymous"`.

```json
{
  "success": true,
  "transaction": "a923c2c0e4fe77061ff1cb882171f6fdf926719bb7f5ffe2e05458438c52825e",
  "network": "bip122:000000000019d6689c085ae165831e93",
  "payer": "anonymous"
}
```

## Error Vocabulary

Facilitators MUST use the following stable strings in `invalidReason` and
`errorReason`. Settlement MUST preserve the verification reason when re-verification
fails.

| Reason | Meaning |
|---|---|
| `unsupported_scheme` | Either side is not `exact`. |
| `network_mismatch` | `accepted.network` differs from the requirement. |
| `unsupported_network` | The concrete BIP-122 network is unsupported. |
| `invalid_exact_bip122_asset` | Either side does not specify `BTC`. |
| `invalid_exact_bip122_pay_to_mismatch` | Either `payTo` value is not `"merchant"`. |
| `invalid_exact_bip122_payment_method` | Either payment method is missing or not `lightning`. |
| `invalid_exact_bip122_invoice_missing` | Either required invoice copy is absent. |
| `invalid_exact_bip122_invoice_mismatch` | The original and accepted invoice copies are not byte-identical. |
| `invalid_exact_bip122_invoice_decode_failed` | Strict BOLT11 decoding, signature validation, or integral-msat validation failed. |
| `invalid_exact_bip122_invoice_currency_mismatch` | BOLT11 currency does not match the network. |
| `invalid_exact_bip122_invoice_amount_mismatch` | BOLT11 amount differs from the required millisatoshis. |
| `invalid_exact_bip122_max_timeout` | `maxTimeoutSeconds` is not a positive integer. |
| `invalid_exact_bip122_invoice_expiry_mismatch` | BOLT11 expiry does not equal `maxTimeoutSeconds`. |
| `invalid_exact_bip122_invoice_created_in_future` | BOLT11 creation time exceeds validation time plus the clock-skew allowance. |
| `duplicate_settlement` | The payment hash is already used or lost an atomic settlement race. |
| `invalid_exact_bip122_preimage_missing` | `payload.preimage` is absent. |
| `invalid_exact_bip122_preimage_malformed` | Preimage contains non-lowercase-hex characters. |
| `invalid_exact_bip122_preimage_length` | Decoded preimage is not exactly 32 bytes. |
| `invalid_exact_bip122_preimage_hash_mismatch` | SHA-256 of the preimage does not equal the payment hash. |
| `invalid_exact_bip122_invoice_expired` | The paid-but-expired settlement-time window was exceeded. |

Client and server implementations SHOULD use these stable local failure reasons.
They are not facilitator response reasons unless a transport explicitly maps a local
failure into one:

| Reason | Meaning |
|---|---|
| `exact_bip122_invoice_issuance_denied` | The server's issuance limiter denied a new invoice. |
| `invalid_exact_bip122_payer_invoice_mismatch` | The payer adapter returned a different invoice. |
| `invalid_exact_bip122_payer_payment_hash_mismatch` | The payer adapter returned a different payment hash. |
| `invalid_exact_bip122_payer_amount_mismatch` | The payer adapter returned a different amount. |
| `exact_bip122_payment_in_flight` | Payment is still in flight and may be retried. |
| `exact_bip122_payment_not_paid` | The payer did not report a paid status. |
| `invalid_exact_bip122_payer_preimage_required` | A paid result omitted the mandatory preimage. |
| `invalid_exact_bip122_payer_preimage_malformed` | A payer preimage is not 64 lowercase hex characters. |
| `invalid_exact_bip122_payer_preimage_hash_mismatch` | A payer preimage does not hash to the invoice payment hash. |

## Security Considerations

### Mandatory Cryptographic Proof

The preimage is bearer proof of payment. Implementations MUST avoid logging or
otherwise disclosing it. A client MUST submit it only to the resource server for the
invoice it paid. Requiring it excludes payer nodes that do not make the preimage
available, but it also enables universal verification without receiver credentials.

### Invoice Substitution

The original and accepted requirements MUST contain the byte-identical invoice.
Checking only the payment hash or amount would let a client substitute a
self-issued invoice and present a known preimage.

### Invoice Issuance Denial of Service

Fresh invoices consume receiver node resources. Servers SHOULD rate-limit or
authorize invoice issuance before calling the receiver. Reusing one invoice across
clients is not an acceptable mitigation: it breaks attribution and creates
first-payer-wins behavior in which one payment can satisfy multiple challenges.

### Network and Currency Confusion

Servers, clients, and facilitators MUST map the concrete BIP-122 network to the
expected BOLT11 currency and reject mismatches. In particular, a `tb` testnet
invoice MUST NOT appear under the mainnet identifier.

### Replay and Multi-instance Deployment

An in-memory replay store is safe only within one process. Multi-process or
multi-instance facilitators MUST use a shared store with an atomic check-and-set;
otherwise the same payment can settle once per process or instance. For example, a
Redis implementation can use `SET <payment_hash> 1 NX EX <ttl>` and treat a null
response as a duplicate.

### Payer Anonymity

Lightning routing does not give a facilitator a stable payer identity. Facilitators
MUST return `payer == "anonymous"` and MUST NOT infer payer identity from `payTo` or
the invoice payee.

## References

- [x402 protocol specification v2](../../x402-specification-v2.md)
- [BOLT11 payment encoding](https://github.com/lightning/bolts/blob/master/11-payment-encoding.md)
- [CAIP-2 chain identification](https://chainagnostic.org/CAIPs/caip-2)
