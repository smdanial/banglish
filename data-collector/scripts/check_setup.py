#!/usr/bin/env python3
"""Check that Supabase is set up correctly and that the public key is insert-only.

Usage (from the repo folder, with .env filled in):
    python3 scripts/check_setup.py

Needs SUPABASE_URL and SUPABASE_ANON_KEY. If SUPABASE_SERVICE_ROLE_KEY is also set, it verifies the
test row/file really landed and then deletes them again. Nothing secret is printed.
"""
import json
import sys
import uuid

from sbhttp import Client, env, load_dotenv

BUCKET = "recordings"


def main():
    load_dotenv()
    url = env("SUPABASE_URL")
    bucket = env("SUPABASE_BUCKET", required=False) or BUCKET
    anon = Client(url, env("SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY"))
    admin_key = env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY", required=False)

    speaker = "check-" + uuid.uuid4().hex[:12]
    path = f"{speaker}/selftest.webm"
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))

    s, b = anon.request("POST", f"/storage/v1/object/{bucket}/{path}", body=b"\x1a\x45\xdf\xa3test",
                        headers={"Content-Type": "audio/webm"})
    check("public key CAN upload audio", s == 200, f"HTTP {s} {b[:200]!r}")

    row = {"speaker_id": speaker, "prompt_id": "selftest", "prompt_text": "self test",
           "actual_text": "self test", "category": "selftest", "audio_path": path,
           "duration_sec": 0.1, "mime_type": "audio/webm", "user_agent": "check_setup.py",
           "consent_version": "selftest"}
    s, b = anon.request("POST", "/rest/v1/recordings", body=row, headers={"Prefer": "return=minimal"})
    check("public key CAN insert a metadata row", s == 201, f"HTTP {s} {b[:200]!r}")

    s, b = anon.request("GET", f"/rest/v1/recordings?select=id&speaker_id=eq.{speaker}")
    readable = s == 200 and json.loads(b or b"[]") != []
    check("public key can NOT read rows", not readable, f"HTTP {s} {b[:200]!r}")

    s, b = anon.request("DELETE", f"/rest/v1/recordings?speaker_id=eq.{speaker}",
                        headers={"Prefer": "return=representation"})
    deleted = s in (200, 204) and json.loads(b or b"[]") != []
    check("public key can NOT delete rows", not deleted, f"HTTP {s} {b[:200]!r}")

    s, b = anon.request("PATCH", f"/rest/v1/recordings?speaker_id=eq.{speaker}", body={"actual_text": "x"},
                        headers={"Prefer": "return=representation"})
    updated = s in (200, 204) and json.loads(b or b"[]") != []
    check("public key can NOT edit rows", not updated, f"HTTP {s} {b[:200]!r}")

    s, b = anon.request("GET", f"/storage/v1/object/{bucket}/{path}")
    check("public key can NOT download audio", s != 200, f"HTTP {s}")

    s, b = anon.request("GET", f"/storage/v1/object/public/{bucket}/{path}")
    check("bucket is NOT public", s != 200, f"HTTP {s}")

    s, b = anon.request("POST", f"/storage/v1/object/list/{bucket}", body={"prefix": speaker})
    listed = s == 200 and json.loads(b or b"[]") != []
    check("public key can NOT list audio files", not listed, f"HTTP {s} {b[:200]!r}")

    s, b = anon.request("DELETE", f"/storage/v1/object/{bucket}", body={"prefixes": [path]})
    removed = s == 200 and json.loads(b or b"[]") != []
    check("public key can NOT delete audio", not removed, f"HTTP {s} {b[:200]!r}")

    s, b = anon.request("POST", f"/storage/v1/object/{bucket}/{path}", body=b"overwrite",
                        headers={"Content-Type": "audio/webm", "x-upsert": "true"})
    check("public key can NOT overwrite audio", s != 200, f"HTTP {s}")

    if admin_key:
        admin = Client(url, admin_key)
        s, b = admin.request("GET", f"/rest/v1/recordings?select=id,audio_path&speaker_id=eq.{speaker}")
        check("admin key sees the test row", s == 200 and len(json.loads(b)) == 1, f"HTTP {s} {b[:200]!r}")
        s, b = admin.request("GET", f"/storage/v1/object/{bucket}/{path}")
        check("admin key can download the test file", s == 200, f"HTTP {s}")
        admin.request("DELETE", f"/rest/v1/recordings?speaker_id=eq.{speaker}")
        admin.request("DELETE", f"/storage/v1/object/{bucket}", body={"prefixes": [path]})
        print("Cleaned up the test row and file.")
    else:
        print(f"(No admin key set: delete the test row/file for speaker '{speaker}' by hand in the dashboard.)")

    ok = all(results)
    print("\nALL GOOD" if ok else "\nSOMETHING IS WRONG - see FAIL lines above")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
