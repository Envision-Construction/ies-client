"""Shared QBO/IES client: safe token handling (rotation persisted BEFORE use),
machine-shared access-token cache (prevents concurrent-session refresh races),
and invalid_grant recovery via previous secret versions.

For full Python environments with the Cloud SDK (`gcloud`) available. For
bare-container Cloud Run jobs (no `gcloud`, no extra pip deps), use
`qbo_client_rest.py` instead -- same public shape, built on the GCE metadata
server + raw Secret Manager REST calls.

Multi-entity: the IES account has one Intuit app (shared qbo-client-id/secret)
connected to multiple company files. Select with company="envision" (default)
or company="enspire", or set QBO_COMPANY in the environment. Per-company
realm/refresh-token secrets and token caches keep the entities isolated —
IAM on the per-company secrets is the access-control boundary.

Consumers as of 2026-08-18: gcpay-sync, qbo-envision-bq-sync, qbo-token-refresher.
Originally lived inside gcpay-sync's own package; extracted here because it has
nothing to do with GCPay specifically and multiple unrelated services depend
on it -- see README for the full backstory.
"""
import base64, json, os, shutil, subprocess, time, urllib.parse, urllib.request, urllib.error

PROJECT = "claude-mcp-457317"
GCLOUD = shutil.which("gcloud")

COMPANIES = {
    "envision": {"realm": "qbo-realm-id", "refresh": "qbo-refresh-token",
                 "cache": ".qbo_token_cache.json"},
    "enspire": {"realm": "qbo-enspire-realm-id", "refresh": "qbo-enspire-refresh-token",
                "cache": ".qbo_token_cache_enspire.json"},
}
DEFAULT_COMPANY = os.environ.get("QBO_COMPANY", "envision").lower()


def _company(company):
    name = (company or DEFAULT_COMPANY).lower()
    if name not in COMPANIES:
        raise ValueError(f"unknown QBO company {name!r} — one of {sorted(COMPANIES)}")
    return name, COMPANIES[name]


def _cache_path(cfg):
    # Machine-shared cache: all sessions reuse one access token instead of racing refresh grants.
    return os.path.join(os.path.expanduser("~"), ".claude", cfg["cache"])


def _rd(secret, version="latest"):
    return subprocess.run([GCLOUD, "secrets", "versions", "access", version,
                           f"--secret={secret}", f"--project={PROJECT}"],
                          capture_output=True, check=True).stdout.decode().strip()

def _wr(secret, value):
    subprocess.run([GCLOUD, "secrets", "versions", "add", secret, "--data-file=-",
                    f"--project={PROJECT}"], input=value.encode(), capture_output=True, check=True)

def _versions(secret):
    out = subprocess.run([GCLOUD, "secrets", "versions", "list", secret,
                          f"--project={PROJECT}", "--filter=state=enabled",
                          "--format=value(name)", "--limit=4"],
                         capture_output=True, check=True).stdout.decode().split()
    return out  # newest first

def _grant(basic, rt):
    body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": rt}).encode()
    req = urllib.request.Request("https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        data=body, method="POST", headers={"Authorization": f"Basic {basic}",
        "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req).read())

def get_access(company=None):
    """Returns (access_token, realm) for the selected company. Shared cache first;
    refresh-grants only when expired. On invalid_grant, falls back through recent
    secret versions (Intuit grace validity) before giving up — a concurrent
    session's rotation may have superseded 'latest'."""
    name, cfg = _company(company)
    cache = _cache_path(cfg)
    realm = _rd(cfg["realm"])
    if os.path.exists(cache):
        try:
            c = json.load(open(cache))
            if c.get("realm") == realm and c.get("exp", 0) > time.time() + 120:
                return c["access"], realm
        except Exception:
            pass
    cid, csec = _rd("qbo-client-id"), _rd("qbo-client-secret")
    basic = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    last_err = None
    for ver in _versions(cfg["refresh"]):
        rt = _rd(cfg["refresh"], ver)
        try:
            tok = _grant(basic, rt)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 400:
                continue  # superseded rotation — try an earlier version
            raise
        new_rt = tok.get("refresh_token", "")
        if new_rt and new_rt != _rd(cfg["refresh"]):
            _wr(cfg["refresh"], new_rt)   # persist rotation FIRST, before any use
        acc = tok["access_token"]
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump({"access": acc, "exp": time.time() + int(tok.get("expires_in", 3600)),
                   "realm": realm}, open(cache, "w"))
        return acc, realm
    raise RuntimeError(f"all {name} refresh-token versions rejected — Intuit re-consent needed; "
                       f"contact the QBO connection owner (Dario, dtomic@envsn.com): {last_err}")

def query(sql, company=None):
    acc, realm = get_access(company)
    u = f"https://quickbooks.api.intuit.com/v3/company/{realm}/query?query={urllib.parse.quote(sql)}&minorversion=75"
    rq = urllib.request.Request(u, headers={"Authorization": f"Bearer {acc}", "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(rq).read())["QueryResponse"]

def post(entity, payload, company=None):
    acc, realm = get_access(company)
    u = f"https://quickbooks.api.intuit.com/v3/company/{realm}/{entity}?minorversion=75"
    rq = urllib.request.Request(u, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {acc}", "Accept": "application/json",
                 "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(rq).read())
