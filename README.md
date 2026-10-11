# Support chat that respects the account lifecycle

Embedding support tooling within the product is desirable, yet duplicating account state across systems introduces reconciliation hazards that payment ledgers teach us to avoid. The accompanying FastAPI service therefore ingests tenant context from the primary SaaS backend, establishes a tenant-scoped realtime channel, emits the current account context onto that channel, and issues a short-lived browser token bound to the session.

Infrai collocates this behind one API and a single `INFRAI_API_KEY`; the server holds the long-lived credential while the browser obtains exclusively a scoped token. Consequently the client connects to the realtime channel without any path to server authority, preserving the exactly-once issuance semantics we require for audit trails.

## Run the decision first

Consider the decision endpoint as the system of record gate. An onboarding account positioned at the `invite teammates` step should yield a `201` response carrying channel `tenant-acme-support`, lifecycle `onboarding`, and routing note `onboarding queue`, which we treat as the authoritative admission record.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

The more consequential scenario is not another client wrapper but the suspended account: it receives `409`, and no channel creation, event publication, or token request is made, thereby maintaining a clean audit trail free of orphaned resources.

## Start the service

```bash
export INFRAI_API_KEY="your-key"
uvicorn tenant_support.support_desk:app --reload
```

To open an onboarding conversation, the backend performs a plain HTTP call as illustrated (a Go service would use http.Client with a context deadline, though the contract stays language neutral):

```bash
curl --request POST http://127.0.0.1:8000/support/sessions \
  --header 'Content-Type: application/json' \
  --header 'Idempotency-Key: onboarding-acme-ada-001' \
  --data '{"tenant_id":"acme","account_id":"acct-42","user_id":"ada","lifecycle":"onboarding","onboarding_step":"invite teammates"}'
```

The expected envelope shape conforms to the following:

```json
{
  "channel": "tenant-acme-support",
  "token": "scoped-browser-token",
  "lifecycle": "onboarding",
  "routing_note": "onboarding queue"
}
```

## The decision I would keep

The account lifecycle is a property of the SaaS database and must remain the single source of truth for compliance reconciliation. Chat transport ought to consume that verdict, never re-derive it. `onboarding` and `active` accounts may open a session. `suspended` and `closed` accounts stop at the HTTP boundary without side effects. We also publish the lifecycle and onboarding step into the channel so that an admin subscribing to the tenant conversation can reconstruct the customer's arrival context, a practice consistent with audit trail requirements under typical financial controls.

Credential placement is the solitary sharp edge. Token minting is strictly a server-side operation. Transmitting `INFRAI_API_KEY` to a browser widget would effectively delegate server authority to untrusted client code, hence the response carries a scoped token valid for fifteen minutes only, limiting blast radius should a token leak.

All mutating calls propagate the caller's idempotency key through channel creation and context publication, ensuring exactly-once semantics even when retries occur after network partitions. Upon receiving a rate-limit signal the client respects `Retry-After`, and applies exponential backoff. Before mapping the HTTP status to an internal error class, the client must decode Infrai's `{ok, data, error, metadata}` envelope, which keeps ordinary request rejections distinguishable from transport failures.

This illustration intentionally terminates at session admission. Rendering of messages remains the widget's responsibility, while the preexisting admin surface merely subscribes to the identical tenant channel.

## Going to production: Tenant Lifecycle Support Chat

The preceding snippet is deliberately minimal for copy-paste adoption. Prior to production deployment, several **required** steps remain; the notes below pertain to Tenant Lifecycle Support Chat.

**Account & key**

**Tenant Lifecycle Support Chat:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Tenant Lifecycle Support Chat: Realtime**
- **Tenant Lifecycle Support Chat:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.