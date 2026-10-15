# ies-client

ies-client is a stdlib-only Python library that issues Intuit Enterprise Suite (QuickBooks Online) access tokens
for a named entity and rotates that entity's refresh token in Secret Manager. It is not a deployed service and
holds no accounting logic: the jobs and services that read or write bills, vendors, purchase orders or invoices
live in the repositories that install it.

## Layout
- `src/ies_client/qbo_client.py`: variant for environments with the Cloud SDK. Reads and writes secrets through
  the `gcloud` CLI and keeps a per-entity access-token cache file under the user's home directory.
- `src/ies_client/qbo_client_rest.py`: variant for bare containers. Uses the GCE metadata server and the Secret
  Manager REST API, needs nothing beyond the standard library, and doubles as a per-entity refresh health check
  (`python -m ies_client.qbo_client_rest`).
- `src/ies_client/__init__.py`: empty; callers import one of the two variant modules directly.
- `pyproject.toml`: setuptools packaging, `src` layout, empty `dependencies` list.
- `README.md`: why the library exists, the rotation pattern, the IAM roles on the refresh-token secrets, the
  install line.

Both variants expose the same API: `get_access(company)` returns `(access_token, realm)`, `query(sql, company)`
returns the QBO `QueryResponse`, and `post(entity, payload, company)` returns the QBO response body. Entities are
the keys of `COMPANIES`; each has its own realm, refresh-token and Intuit client-credential secrets.

## Build and check
- Install for local work: `pip install -e .` (setuptools build from `pyproject.toml`).
- The repository has no test suite, lint configuration or CI workflow. A change to `get_access` is unverified
  unless the PR adds a test that stubs Secret Manager and the Intuit token endpoint.
- `python -m ies_client.qbo_client_rest` calls Intuit with real credentials and can rotate real refresh tokens.
  Run it only under the service identity meant for it, never as a casual smoke test.

## Release model
This is a library with no deploy step of its own. Its consumers install it as a git dependency of the default
branch with no tag, so merging to `main` releases it to each of them on their next build. Some bare-container jobs paste `qbo_client_rest.py` into their own script instead of installing it; those
copies change only when their owners re-copy the file.
- Keep every change backward compatible: function names, parameter order (callers pass `company` positionally),
  `COMPANIES` keys and return shapes.
- Change both variant modules in the same PR.

## Local invariants
- Rotation is persisted before use. In `get_access`, after a successful grant, when Intuit returns a refresh token
  that differs from the current newest secret version, the code adds it as a new version (`_wr` in the gcloud
  variant, `_sm_add` in the REST variant) and only then returns the access token; the gcloud variant also writes
  its access-token cache only after that write. A failed write raises, so no access token is returned.
- Refresh tokens are read fresh from Secret Manager for every grant and never cached; the gcloud variant's cache
  file holds only the access token, its expiry and the realm.
- On an Intuit HTTP 400 the loop moves to the next older enabled secret version, newest first, and raises a
  re-consent error only when every listed version fails. The branch checks only the status code, so any other 400
  from the token endpoint also ends as that error. Any other HTTP error is raised at once.
- Never print, log or return refresh tokens, client secrets or the Basic authorization value. Only `get_access`
  returns a token, and only the access token.
- Name the entity explicitly in new code. `DEFAULT_COMPANY` (from `QBO_COMPANY`, else `envision`) still exists
  because an installed consumer calls `query(sql)` without `company`; removing it needs that consumer changed
  first.
- Entities stay isolated: each has its own secrets and its own cache file, and per-secret IAM is the access
  boundary.
- No third-party dependencies, and `qbo_client_rest.py` keeps working as a single pasted file.
- This repository is public. New code, comments and docs add no cloud project ids, personal contacts, internal
  hostnames or secret values.

## Portfolio
This repository is part of the Envision Construction portfolio. Inside this repository, this file wins.
Never, in any session:
- Deploy a Cloud Build-triggered service by hand or write out a manual deploy command for one. Ship by
  merging to the default branch, or re-run the trigger.
- Read live database schemas or rows into code graphs, docs, commits, reviews or memory.
- Report a financial figure without a named entity; ask which entity first.
- Add a call or write path on a deprecated system (Procore, Sage Intacct, Brex).
- Commit or print secrets, tokens or personal data.
Ask first, and wait for an explicit yes: a push to main, a force-push, a visibility change.
Before a change that crosses this repository's boundary (deploy path, another repository's API or data, auth,
ownership), read https://github.com/Envision-Construction/central-command/blob/main/ORIENTATION.md and this
repository's row in central-command `repo-manifest.json`; check the live trigger list rather than any prose.
