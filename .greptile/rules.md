# ies-client review standards

ies-client is a stdlib-only Python library that issues Intuit Enterprise Suite (QuickBooks Online) access tokens
for a named entity and rotates that entity's refresh token in Secret Manager. It is not a deployed service or a
data-sync job: it holds no bill, vendor or invoice logic, and the repositories that install it own those jobs.

## Invariants that need explanation
- Intuit invalidates the previous refresh token when it issues a new one. Why: if a process exits between the
  grant and the write-back, the new token is stored nowhere, and the entity can be left needing a fresh human
  consent in Intuit.
  Source: `get_access` in `src/ies_client/qbo_client.py` and `src/ies_client/qbo_client_rest.py`.
  A violating diff hands the access token back first and persists afterwards, or logs a failed write and goes on.
- Several processes share each entity's refresh token, so the newest version can be superseded between the read
  and the grant. Why: without stepping back through recent enabled versions, a concurrent rotation looks like a
  dead connection. Source: the HTTP 400 branch inside `get_access`. That branch checks only the status code, so
  any other 400 from the token endpoint also ends as the re-consent error; a diff may narrow it to
  `invalid_grant`, but must keep the step-back. A violating diff retries one version only, or turns every 400 into a hard failure.
- The two modules are interchangeable at run time. Why: callers load the REST module when the metadata server
  answers and the gcloud module otherwise, so one call has to mean the same thing in both. Source: `query` and
  `post` in both modules. Known gap: only the REST `post` attaches the QBO fault body to its HTTPError; a diff that
  edits either `post` should close that gap, not widen it.
- `DEFAULT_COMPANY` (from `QBO_COMPANY`, else the `envision` entry) survives because an installed caller still
  calls `query` without naming an entity. Why: deleting the default before that caller changes breaks it on its
  next build. Source: `_company` in both modules. A violating diff deletes the default while that caller still
  depends on it, or quietly points it at a different entity.
- The repository is public. Why: anything added here is readable by anyone. A violating diff adds a cloud project
  id, a person's contact or an internal hostname to code, comments or docs.

## Generated or vendored (review the generator, not the output)
- Nothing here is generated or vendored. The reverse holds: `src/ies_client/qbo_client_rest.py` is pasted whole
  into bare-container job scripts elsewhere, and those copies change only when their owners re-copy the file, so
  a PR that changes its behavior says so in the description.
