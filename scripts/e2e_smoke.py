"""End-to-end smoke test for the dockerized ai-delivery-assistant stack.

Run it on the host against the stack started by compose.yml (the app is
published on 127.0.0.1:8001, loopback only, because POST /api/auth/setup
creates the first admin):

    set -a && . ./.env && set +a          # provides BOOTSTRAP_TOKEN
    python scripts/e2e_smoke.py

Checks, in order:
  1. GET  /api/health       liveness; 200 with {"analysis_ready": bool}.
                              analysis_ready is false without a working
                              NVIDIA_API_KEY — reported, not failed, because
                              the analysis route is best-effort.
  2. POST /api/auth/setup    first admin, gated by BOOTSTRAP_TOKEN. A 400
                              "already completed" is fine: the user exists,
                              so the script falls back to login.
  3. POST /api/auth/login    bearer token for the smoke user.
  4. GET  /api/auth/me       the token is accepted.
  5. GET  /api/projects      an authenticated JSON surface answers from the
                              real PostgreSQL behind the stack (not the test
                              harness' SQLite).
  6. GET  /                  the built SPA index.html is served.

Exit 0 iff every check passes; exit 1 with a per-check report otherwise.
Stdlib only, so it runs on the host or inside any container with Python.

Configuration (environment):
  BASE_URL        default http://127.0.0.1:8001
  SMOKE_USER      default e2e-admin
  SMOKE_PASS      default e2e-pass-1234 (>= 8 chars, the API minimum)
  BOOTSTRAP_TOKEN required for check 2 on a fresh database
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8001")
USERNAME = os.environ.get("SMOKE_USER", "e2e-admin")
PASSWORD = os.environ.get("SMOKE_PASS", "e2e-pass-1234")
BOOTSTRAP_TOKEN = os.environ.get("BOOTSTRAP_TOKEN", "")

TIMEOUT = 10
ALLOWED_SCHEMES = ("http",)
OPENER = urllib.request.build_opener()

_failures: list[str] = []


def open_url(req: urllib.request.Request):
    """Open one request, refusing any URL outside the permitted schemes."""
    scheme = urllib.parse.urlsplit(req.full_url).scheme
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"refusing to open {req.full_url!r}: "
            f"scheme must be {' or '.join(ALLOWED_SCHEMES)}, got {scheme!r}"
        )
    return OPENER.open(req, timeout=TIMEOUT)


def request_json(url: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    """POST (payload given) or GET; returns (status, body-dict).

    A dead or unreachable server comes back as (0, {"error": ...}) so the
    caller reports a failed check instead of crashing with a traceback.
    """
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        resp = open_url(req)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        body = err.read().decode()
        try:
            parsed: dict = json.loads(body)
            return err.code, parsed
        except json.JSONDecodeError:
            return err.code, {"raw": body[:200]}
    except urllib.error.URLError as err:
        return 0, {"error": f"unreachable: {err.reason}"}


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)
    return ok


def main() -> int:
    print(f"e2e smoke against {BASE} (user={USERNAME})")

    # 1. liveness
    status, body = request_json(f"{BASE}/api/health")
    ready = status == 200 and isinstance(body.get("analysis_ready"), bool)
    check("GET /api/health", ready, f"{status} analysis_ready={body.get('analysis_ready')} reason={body.get('reason')}")
    if not ready:
        print("\nstack is not healthy — stopping before auth checks")
        return 1

    # 2. first admin (or reuse the existing one)
    status, body = request_json(
        f"{BASE}/api/auth/setup",
        {"username": USERNAME, "password": PASSWORD, "bootstrap_token": BOOTSTRAP_TOKEN},
    )
    if status in (200, 201) and body.get("access_token"):
        created = body.get("user", {}).get("username", "?")
        check("POST /api/auth/setup", True, f"created admin {created}")
        token = body["access_token"]
    elif status == 400 and "already completed" in str(body.get("detail", "")):
        check("POST /api/auth/setup", True, "already completed (rerun) — falling back to login")
        token = None
    else:
        check("POST /api/auth/setup", False, f"{status} {body} (is BOOTSTRAP_TOKEN set and correct?)")
        return 1

    # 3. login (also validates the setup fallback path)
    status, body = request_json(f"{BASE}/api/auth/login", {"username": USERNAME, "password": PASSWORD})
    if status == 200 and body.get("access_token"):
        check("POST /api/auth/login", True, f"role={body.get('user', {}).get('role')}")
        token = body["access_token"]
    else:
        check("POST /api/auth/login", False, f"{status} {body}")
        return 1

    # 4. token accepted
    status, body = request_json(f"{BASE}/api/auth/me", token=token)
    check("GET /api/auth/me", status == 200 and body.get("username") == USERNAME, f"{status} {body}")

    # 5. authenticated JSON surface answers from the stack database
    status, body = request_json(f"{BASE}/api/projects", token=token)
    check("GET /api/projects", status == 200 and "projects" in body, f"{status} projects={len(body.get('projects', []))}")

    # 6. SPA served
    req = urllib.request.Request(f"{BASE}/")
    try:
        resp = open_url(req)
        html = resp.read().decode()
        ok = resp.status == 200 and ("<div" in html or "<script" in html)
        check("GET / (SPA index)", ok, f"{resp.status} bytes={len(html)}")
    except urllib.error.HTTPError as err:
        check("GET / (SPA index)", False, f"{err.code}")

    print(f"\n{'ALL CHECKS PASSED' if not _failures else 'FAILED: ' + ', '.join(_failures)}")
    return 0 if not _failures else 1


if __name__ == "__main__":
    sys.exit(main())