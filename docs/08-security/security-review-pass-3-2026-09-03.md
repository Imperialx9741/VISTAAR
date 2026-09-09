VISTAAR — Security Review, Pass 3 (targeted negative testing)

Date: 2026-09-03
Reviewer: Claude Code (code-level review, not a substitute for an external
audit or penetration test — see security-review-2026-09-02.md §7, which
applies equally here)
Scope: item 3 of the 2026-09-03 production-readiness instruction —
"continue targeted security hardening/negative testing for sensitive
endpoints, especially authorization, money, webhooks, uploads, and
replay/idempotency." Unlike pass 1 and pass 2 (which reviewed code by
reading it), this pass's method is to write and run adversarial tests
against those five categories, on top of the coverage passes 1–2 already
confirmed, and fix anything a test catches.

1. Summary

| # | Category | Result |
| :-- | :-- | :-- |
| 1 | Authorization (uploads) | **Gap closed** — added a negative test; code was already correct |
| 2 | Replay/idempotency | **Gap closed** — added a negative test; code was already correct |
| 3 | Money | **Gap closed** — added a negative test; code was already correct |
| 4 | Webhooks | **Real bug found and fixed** — malformed JSON crashed the endpoint with an unhandled 500 |
| 5 | Uploads (input validation) | **Confirmed clean** — no action needed |

2. Real bug found and fixed

2.1 [MEDIUM] Razorpay webhook returned an unhandled 500 on malformed JSON

`POST /wallet/webhooks/razorpay` (`src/modules/wallet/router.py`) is the
one endpoint in the entire router layer that reads a request body
manually (`await request.json()`) instead of through a Pydantic model —
every other endpoint gets FastAPI's automatic, clean 422 on malformed
JSON for free because its body is a validated Pydantic type. This one
endpoint had no equivalent guard: a POST with a syntactically invalid
JSON body but a valid-shaped Razorpay signature header raised an
unhandled `json.decoder.JSONDecodeError`, propagating through the
Sentry/Starlette exception-handling stack as a raw, unstructured 500 —
not the structured `422 VALIDATION_FAILED` envelope every other endpoint
in this codebase returns for a malformed request.

Reproduced directly (not just reasoned about): a script posting
`content=b"not-json-garbage"` against a real `TestClient` with a
signature computed to be valid for that raw body produced the full
unhandled-exception traceback.

Fixed: wrapped the `await request.json()` call in
`try/except json.JSONDecodeError`, returning the same structured
`422 VALIDATION_FAILED` envelope (`error_envelope(...)` +
`http_status_for_error_code(...)`) every other endpoint uses for a
malformed request — see `src/modules/wallet/router.py`'s
`razorpay_webhook` handler. Confirmed via a repo-wide grep
(`await request.json()|await request.body()` across every
`src/modules/*/router.py`) that this is the only occurrence of the
unguarded-`request.json()` pattern anywhere in the router layer; the one
other raw-body read in the same file (`await request.body()`, used to
recompute the HMAC signature) was already safe, since reading raw bytes
cannot raise a decode error the way parsing JSON can.

New regression test: `test_webhook_rejects_malformed_json_cleanly`
(`tests/test_wallet_recharge_api.py`) — posts a syntactically invalid
body with a signature computed to match it, asserts a `422
VALIDATION_FAILED` response instead of a 500.

3. Gaps closed (code was already correct, just untested)

3.1 Authorization — GPS dispute evidence upload

`test_unrelated_account_cannot_request_an_evidence_upload_url`
(`tests/test_gps_dispute_api.py`) — confirms an account that is neither
the ride's customer nor its driver gets `404` (not `403`, per this
codebase's consistent "don't reveal existence" IDOR convention already
documented in security-review-pass-2-2026-09-03.md §2.1) when requesting
a presigned upload URL for another ride's dispute evidence. The handler
already enforced this correctly; it simply had no test.

3.2 Replay/idempotency — cross-request idempotency-key reuse

`test_accept_offer_reusing_an_idempotency_key_for_a_different_offer_is_rejected`
(`tests/test_matching_api.py`) — confirms that reusing the same
`Idempotency-Key` header value against a *different* ride offer than the
one it was first used for is rejected, rather than silently replaying
the first offer's result or accepting the second offer under the first
one's key. The existing idempotency-key infrastructure
(`shared.idempotency`) already scoped keys correctly; this was
previously untested at the API layer for this specific endpoint.

3.3 Money — negative recharge amount

`test_create_recharge_order_rejects_a_negative_amount`
(`tests/test_wallet_recharge_api.py`) — confirms `POST
/wallet/recharge-orders` rejects a negative `amount` with `422` rather
than creating a Razorpay order for it. Pydantic's `Decimal` field
already had the correct constraint; this was previously untested.

4. Confirmed clean (no action needed)

4.1 Uploads — input validation

`RequestUploadUrlBody`/`GpsDisputeEvidenceUploadUrlBody`'s `content_type`
field is a required `str` with no default in both schemas — a missing
field is already rejected by Pydantic's automatic `422` before any
handler code runs; an invalid/unsupported MIME type is rejected at the
`shared.storage` layer (the allow-list check), which existing tests
already exercise. No gap found.

5. What this pass does not do

- Does not re-review categories pass 1/pass 2 already covered
  end-to-end (object-level IDOR, mass assignment, monetary typing,
  promotion/referral races) — this pass is additive negative testing on
  top of that, not a re-audit.
- Does not exhaustively negative-test every endpoint in the codebase;
  targeted at the five categories the instruction named, using a
  survey-then-target method (grep for existing coverage per category,
  write a test only where a real gap was confirmed).
- Does not change the P2P ride-fare model, customer penalty collection,
  or touch iOS/Apple work.
- ~~Does not resolve the presigned-PUT-vs-POST file-upload size-limit
  decision~~ — was out of scope for this pass; resolved separately
  2026-09-03, see security-review-pass-2-2026-09-03.md §3.1 and
  ADR-0065.

6. Verification

- `ruff check` and `mypy` clean on every file touched this pass
  (`src/modules/wallet/router.py`, `tests/test_gps_dispute_api.py`,
  `tests/test_matching_api.py`, `tests/test_wallet_recharge_api.py`).
- Full backend suite (`pytest -q`) run after all changes — see the
  item-3 completion report for the exact pass/fail count.
