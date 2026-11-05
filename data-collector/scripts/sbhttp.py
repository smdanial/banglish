"""Tiny Supabase HTTP helper (standard library only). Shared by the scripts in this folder."""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path=ROOT / ".env"):
    """Load KEY=VALUE lines from .env into os.environ (existing env vars win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def env(*names, required=True):
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    if required:
        raise SystemExit(f"Missing environment variable: {' or '.join(names)} (see .env.example)")
    return None


def auth_headers(key):
    """Legacy JWT keys (eyJ...) go in both headers; new sb_publishable_/sb_secret_ keys only in apikey."""
    h = {"apikey": key}
    if key.startswith("eyJ"):
        h["Authorization"] = f"Bearer {key}"
    return h


class Client:
    def __init__(self, url, key):
        self.url = url.rstrip("/")
        self.key = key

    def request(self, method, path, body=None, headers=None, timeout=120):
        """Returns (status, bytes). Never raises on HTTP errors."""
        h = auth_headers(self.key)
        h.update(headers or {})
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self.url + path, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
