"""Run all demo fixtures live against the local server; print outcomes."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
EXPECTED = {
    "F0": "approved",
    "EC-1": "pending",
    "EC-2": "rejected",
    "EC-3": "pending",
    "EC-4": "pending",
}


def post(path: str) -> dict:
    req = urllib.request.Request(
        BASE + path, method="POST", data=b"", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode())


def wait_done(submission_id: str, timeout_s: float = 300.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        data = get(f"/api/submissions/{submission_id}")
        status = data.get("status")
        if status and status != "running" and data.get("decision"):
            return data
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for {submission_id}")


def main() -> int:
    health = get("/api/health")
    print("health", health)
    results = []
    for name, expected in EXPECTED.items():
        print(f"\n=== Running {name} (expect {expected}) ===")
        started = time.time()
        try:
            created = post(f"/api/fixtures/{name}/run")
            sid = created.get("submission_id") or created.get("id")
            print("submission_id", sid)
            result = wait_done(sid)
            status = result.get("status")
            elapsed = time.time() - started
            decision = result.get("decision") or {}
            hard = decision.get("hard_fails") or []
            pending = [
                p.get("item") for p in (decision.get("pending_items") or [])
            ]
            flags = decision.get("soft_flags") or []
            email = result.get("vendor_email_draft")
            ok = status == expected
            print(f"status={status} expected={expected} ok={ok} elapsed={elapsed:.1f}s")
            print(f"hard_fails={hard}")
            print(f"pending_items={pending}")
            print(f"soft_flags={flags}")
            print(f"email={'yes' if email else 'no'}")
            print(f"summary={decision.get('summary')}")
            audit = result.get("audit") or {}
            print(f"sanctions_source={audit.get('sanctions_source')}")
            results.append((name, ok, status, expected))
        except Exception as exc:
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            results.append((name, False, "error", expected))

    print("\n=== SUMMARY ===")
    all_ok = True
    for name, ok, status, expected in results:
        mark = "PASS" if ok else "FAIL"
        print(f"{mark} {name}: got={status} expected={expected}")
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as exc:
        print("Server not reachable:", exc)
        sys.exit(2)
