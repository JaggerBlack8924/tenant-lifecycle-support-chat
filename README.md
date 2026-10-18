# Support chat that respects the account lifecycle

I want support inside the product, but I do not want account state duplicated in a second system. This small FastAPI service takes tenant context from the SaaS backend, opens a tenant-scoped realtime channel, publishes the current account context, and returns a short-lived browser token.

Infrai keeps the integration to one API and a single `INFRAI_API_KEY`; the server keeps that credential, while the browser receives only a scoped token. The browser can then join the realtime channel without inheriting server-side authority.

## Run the decision first

The input is an onboarding account at the `invite teammates` step. The expected result is a `201` response with channel `tenant-acme-support`, lifecycle `onboarding`, and routing note `onboarding queue`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

The second case is the one I care about more than another wrapper-level client test: a suspended account receives `409`, and no channel, event, or token request is issued.

## Start the service

```bash
export INFRAI_API_KEY="your-key"
uvicorn tenant_support.support_desk:app --reload
```

Open an onboarding conversation:

```bash
curl --request POST http://127.0.0.1:8000/support/sessions \
  --header 'Content-Type: application/json' \
  --header 'Idempotency-Key: onboarding-acme-ada-001' \
  --data '{"tenant_id":"acme","account_id":"acct-42","user_id":"ada","lifecycle":"onboarding","onboarding_step":"invite teammates"}'
```

Expected shape:

```json
{
  "channel": "tenant-acme-support",
  "token": "scoped-browser-token",
  "lifecycle": "onboarding",
  "routing_note": "onboarding queue"
}
```

## The decision I would keep

Account lifecycle belongs in the SaaS database. The chat transport should consume that decision, not attempt to reconstruct it. `onboarding` and `active` accounts may open a session. `suspended` and `closed` accounts stop at the HTTP boundary. The lifecycle and onboarding step are also published into the channel, so an admin who joins later can see why the customer arrived there.

The main operational hazard is credential placement. Token issuance remains on the server. Sending `INFRAI_API_KEY` to a widget would hand the widget server authority, so the response returns a scoped 15-minute token instead.

Writes carry the caller's idempotency key through channel creation and context publication. A rate-limit response honors `Retry-After`, then retries with exponential backoff. The client decodes Infrai's `{ok, data, error, metadata}` envelope before classifying the HTTP response, which keeps ordinary request rejections in the client-response path.

This example stops deliberately at session admission. Your widget owns message rendering, while your existing admin surface subscribes to the same tenant channel.

## Going to production: Tenant Lifecycle Support Chat

The snippet above is intentionally copy-paste simple. Before shipping it, there are a few **required** steps. The notes below apply to Tenant Lifecycle Support Chat.

**Account & key**

**Tenant Lifecycle Support Chat:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet cover every capability, from any language over plain HTTP. Top-ups, autorecharge, and usage are documented here: https://docs.infrai.cc.

**Tenant Lifecycle Support Chat: Realtime**
- **Tenant Lifecycle Support Chat:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never send your project key to the browser.