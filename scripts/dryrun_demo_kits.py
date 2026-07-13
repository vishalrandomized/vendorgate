"""Dry-run New Submission path using demo_kits form.json + PDF uploads."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"

KITS = {
    "F0_happy": "approved",
    "EC-1_ownership": "pending",
}


def multipart(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = "----VendorGateBoundary7MA4YWxkTrZu0gW"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode()
        )
    for name, path in files.items():
        data = path.read_bytes()
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
                f"Content-Type: application/pdf\r\n\r\n"
            ).encode()
            + data
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def post_multipart(path: str, body: bytes, content_type: str) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method="POST",
        headers={"Content-Type": content_type},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode())


def wait_done(submission_id: str, timeout_s: float = 300.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        data = get(f"/api/submissions/{submission_id}")
        if data.get("decision") and data.get("status") != "running":
            return data
        time.sleep(2)
    raise TimeoutError(submission_id)


def run_kit(kit_id: str, expected: str) -> bool:
    folder = ROOT / "demo_kits" / kit_id
    form = (folder / "form.json").read_text()
    files: dict[str, Path] = {"tax_certificate": folder / "tax_certificate.pdf"}
    bank = folder / "bank_proof.pdf"
    if bank.exists():
        files["bank_proof"] = bank
    body, ctype = multipart({"form": form}, files)
    print(f"\n=== {kit_id} (expect {expected}) ===")
    created = post_multipart("/api/submissions", body, ctype)
    sid = created.get("submission_id") or created.get("id")
    print("submission_id", sid)
    result = wait_done(sid)
    status = result.get("status")
    ok = status == expected
    print(f"status={status} ok={ok}")
    print("summary", (result.get("decision") or {}).get("summary"))
    return ok


def main() -> int:
    health = get("/api/health")
    print("health", health)
    kits = get("/api/demo-kits")
    print("demo_kits", [k["id"] for k in kits])
    all_ok = True
    for kit_id, expected in KITS.items():
        try:
            all_ok = run_kit(kit_id, expected) and all_ok
        except Exception as exc:
            print(f"FAIL {kit_id}: {type(exc).__name__}: {exc}")
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as exc:
        print("Server not reachable:", exc)
        sys.exit(2)
