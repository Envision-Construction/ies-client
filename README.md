# ies-client

Shared Intuit Enterprise Suite (QuickBooks Online) OAuth token client for Envision's GCP services. Handles the one thing every QBO/IES-touching job needs and kept reimplementing slightly differently: safely refreshing a shared `qbo-refresh-token` Secret Manager secret without racing other consumers.

## Why this exists

`qbo-refresh-token` (and its Enspire equivalent, `qbo-enspire-refresh-token`) is a single Intuit-issued credential shared across every service that talks to IES. Intuit invalidates the old refresh token whenever a new one is issued, so any consumer using a stale cached copy gets `invalid_grant`. As of 2026-08-18, `qbo-envision-bq-sync` rotates it **hourly** as part of its normal operation — any consumer without a fallback will eventually break.

This logic was originally written once (in `gcpay-sync`), then re-derived from scratch twice more by other jobs as they were built (`qbo-envision-bq-sync`, and a third, incomplete version in `qbo-token-refresher` that was missing the fallback entirely and had been failing silently). None of those three services have anything to do with each other's actual business logic — the only thing they share is needing a QBO access token safely. That's what this repo is for.

## Two variants, same public API (`get_access`, `query`, `post`)

- **`ies_client.qbo_client`** — for full Python environments with the Cloud SDK (`gcloud`) available. Also maintains a local access-token cache to avoid unnecessary refresh calls entirely when a still-valid token exists.
- **`ies_client.qbo_client_rest`** — for bare-container Cloud Run jobs (`python:3.12-slim`, no `gcloud`, no extra pip installs — the `SCRIPT_B64` pattern used by `qbo-envision-bq-sync` and `qbo-token-refresher`). Built on the GCE metadata server + raw Secret Manager REST calls instead. Also runnable directly as a self-contained daily health-check/refresh script (`python -m ies_client.qbo_client_rest`).

Both implement the same safety pattern:
1. Never cache a refresh token across process lifetimes — always read fresh from Secret Manager.
2. On `invalid_grant`, fall back through the last few enabled secret versions (Intuit's grace-validity window) before giving up — a concurrent consumer's rotation may have superseded `latest`.
3. Persist a newly-rotated refresh token back to Secret Manager **immediately**, before returning the access token to the caller.

## IAM required (on `qbo-refresh-token` / `qbo-enspire-refresh-token`)

| Role | Why |
|---|---|
| `roles/secretmanager.secretAccessor` | reading a specific/latest secret version |
| `roles/secretmanager.viewer` | listing versions for the fallback — **not** covered by `secretAccessor` alone. Missing this on `qbo-enspire-refresh-token` broke `qbo-token-refresher` on its first deploy against this client (2026-08-18) despite `qbo-refresh-token` already having it. |
| `roles/secretmanager.secretVersionAdder` (or `secretmanager.admin`) | writing the rotated token back |

## Known consumers

- `gcpay-sync` (GCPay↔QBO bill/PO sync)
- `qbo-envision-bq-sync` (hourly QBO→BigQuery sync)
- `qbo-token-refresher` (daily health-check/refresh job — uses `qbo_client_rest.py`'s `__main__` directly as its Cloud Run job script)

New QBO/IES-touching services should depend on this repo directly rather than writing their own refresh logic.

## Using it

```bash
pip install git+https://github.com/Envision-Construction/ies-client.git
```

```python
from ies_client.qbo_client import get_access, query, post
# or, in a bare-container job:
from ies_client.qbo_client_rest import get_access, query, post

access_token, realm = get_access(company="envision")  # or "enspire"
```

For a `SCRIPT_B64`-style job with no pip install step at all, embed `qbo_client_rest.py`'s content directly into the job's script at deploy/build time rather than hand-rewriting the logic.
