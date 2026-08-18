"""Zero-dependency QBO client for bare-container Cloud Run jobs (python:3.12-slim
SCRIPT_B64 pattern, no gcloud CLI, no extra pip installs).

Same shared-token-safety guarantees as qbo_client.py (persist rotation BEFORE
use, fall back through recent secret versions on invalid_grant), but built on
the GCE metadata server + raw Secret Manager REST calls instead of shelling
out to `gcloud` -- qbo_client.py needs the Cloud SDK present; this doesn't
need anything beyond the stdlib and a Cloud Run/Compute service identity.

Ported from qbo-envision-bq-sync's working inline implementation, hardened
with the version-fallback loop qbo_client.py already has (the bug that hit
qbo-token-refresher: it only ever read `latest` once and gave up on the
first invalid_grant with no retry).

Multi-entity: same COMPANIES convention as qbo_client.py -- company="envision"
(default) or "enspire", or set QBO_COMPANY in the environment.

Drop this file's content into a job's SCRIPT_B64 alongside job-specific logic
(these jobs bake the whole script into an env var at deploy time -- there's
no runtime import path across separate Cloud Run jobs), or run it directly
as the daily health-check/refresh job (see __main__ below).
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

PROJECT = "claude-mcp-457317"
METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "service-accounts/default/token"
)
SM_BASE = f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets"
INTUIT_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

COMPANIES = {
    "envision": {"realm": "qbo-realm-id", "refresh": "qbo-refresh-token"},
    "enspire": {"realm": "qbo-enspire-realm-id", "refresh": "qbo-enspire-refresh-token"},
}
DEFAULT_COMPANY = os.environ.get("QBO_COMPANY", "envision").lower()


def _company(company):
    name = (company or DEFAULT_COMPANY).lower()
    if name not in COMPANIES:
        raise ValueError(f"unknown QBO company {name!r} -- one of {sorted(COMPANIES)}")
    return name, COMPANIES[name]


def _gce_token():
    req = urllib.request.Request(METADATA_TOKEN_URL, headers={"Metadata-Flavor": "Google"})
    return json.loads(urllib.request.urlopen(req).read())["access_token"]


def _sm_get(gtok, secret, version="latest"):
    req = urllib.request.Request(
        f"{SM_BASE}/{secret}/versions/{version}:access",
        headers={"Authorization": f"Bearer {gtok}"},
    )
    payload = json.loads(urllib.request.urlopen(req).read())["payload"]["data"]
    return base64.b64decode(payload).decode().strip()


def _sm_add(gtok, secret, value):
    body = json.dumps({"payload": {"data": base64.b64encode(value.encode()).decode()}}).encode()
    req = urllib.request.Request(
        f"{SM_BASE}/{secret}:addVersion",
        data=body,
        headers={"Authorization": f"Bearer {gtok}", "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req)


def _sm_versions(gtok, secret, limit=4):
    """Most recent `limit` ENABLED versions, newest first."""
    req = urllib.request.Request(
        f"{SM_BASE}/{secret}/versions?filter=state:ENABLED&pageSize={limit * 3}",
        headers={"Authorization": f"Bearer {gtok}"},
    )
    versions = json.loads(urllib.request.urlopen(req).read()).get("versions", [])
    # name is ".../versions/<N>" -- sort numerically descending, don't trust API order
    versions.sort(key=lambda v: int(v["name"].rsplit("/", 1)[1]), reverse=True)
    return [v["name"].rsplit("/", 1)[1] for v in versions[:limit]]


def _grant(basic, refresh_token):
    body = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}
    ).encode()
    req = urllib.request.Request(
        INTUIT_TOKEN_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    return json.loads(urllib.request.urlopen(req).read())


def get_access(company=None):
    """Returns (access_token, realm) for the selected company. On invalid_grant,
    falls back through the last 4 enabled secret versions (Intuit grace validity)
    before giving up -- a concurrent consumer's rotation may have superseded
    'latest' between when we read it and when we tried to use it."""
    name, cfg = _company(company)
    gtok = _gce_token()
    realm = _sm_get(gtok, cfg["realm"])
    cid, csec = _sm_get(gtok, "qbo-client-id"), _sm_get(gtok, "qbo-client-secret")
    basic = base64.b64encode(f"{cid}:{csec}".encode()).decode()

    last_err = None
    for ver in _sm_versions(gtok, cfg["refresh"]):
        rt = _sm_get(gtok, cfg["refresh"], ver)
        try:
            tok = _grant(basic, rt)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 400:
                continue  # superseded rotation -- try an earlier version
            raise
        new_rt = tok.get("refresh_token", "")
        if new_rt and new_rt != _sm_get(gtok, cfg["refresh"]):
            _sm_add(gtok, cfg["refresh"], new_rt)  # persist rotation FIRST, before any use
        return tok["access_token"], realm

    raise RuntimeError(
        f"all {name} refresh-token versions rejected -- Intuit re-consent needed; "
        f"contact the QBO connection owner (Dario, dtomic@envsn.com): {last_err}"
    )


def query(sql, company=None):
    acc, realm = get_access(company)
    url = f"https://quickbooks.api.intuit.com/v3/company/{realm}/query?query={urllib.parse.quote(sql)}&minorversion=75"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {acc}", "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["QueryResponse"]


def post(entity, payload, company=None):
    acc, realm = get_access(company)
    url = f"https://quickbooks.api.intuit.com/v3/company/{realm}/{entity}?minorversion=75"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {acc}", "Accept": "application/json", "Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req).read())


if __name__ == "__main__":
    # Self-contained daily health-check/refresh -- this is the corrected
    # replacement for qbo-token-refresher's current SCRIPT_B64, which only
    # ever tries `latest` once and gives up on the first invalid_grant.
    import sys

    failures = 0
    for name in COMPANIES:
        try:
            acc, realm = get_access(name)
        except Exception as e:
            print(f"{name}: QBO REFRESH FAILED: {e}", file=sys.stderr)
            failures += 1
            continue
        req = urllib.request.Request(
            f"https://quickbooks.api.intuit.com/v3/company/{realm}/companyinfo/{realm}?minorversion=75",
            headers={"Authorization": f"Bearer {acc}", "Accept": "application/json"},
        )
        try:
            cname = json.loads(urllib.request.urlopen(req).read())["CompanyInfo"]["CompanyName"]
            print(f"{name}: refresh OK; company: {cname}")
        except Exception as e:
            print(f"{name}: WARN smoke test failed (refresh itself succeeded): {e}")
    sys.exit(1 if failures else 0)
