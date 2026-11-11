"""Any OpenAI-compatible chat API that accepts audio (Gemini by default)."""
from __future__ import annotations

import base64
import os


def resolve(cfg: dict):
    """-> (base_url, api_key, model, reason_if_unusable)"""
    key_envs = cfg.get("api_key_env") or ["GEMINI_API_KEY"]
    if isinstance(key_envs, str):
        key_envs = [key_envs]
    api_key = next((os.environ[k] for k in key_envs if os.environ.get(k)), None)
    model = os.environ.get(cfg.get("model_env") or "", "") or cfg.get("default_model")
    reason = None
    try:
        import openai  # noqa: F401
    except ImportError:
        reason = "openai package not installed (pip install -r eval/requirements.txt)"
    if not api_key:
        reason = f"no API key ({' or '.join(key_envs)} not set in .env / environment)"
    elif not model:
        reason = f"no model name ({cfg.get('model_env')} not set)"
    return cfg.get("base_url"), api_key, model, reason


def make_client(cfg: dict):
    base_url, api_key, model, reason = resolve(cfg)
    if reason:
        return None, None, reason
    from openai import OpenAI
    return OpenAI(base_url=base_url, api_key=api_key, max_retries=5, timeout=120), model, None


class OpenAICompatModel:
    def __init__(self, cfg: dict):
        self.client, self.model, reason = make_client(cfg)
        if reason:
            raise RuntimeError(reason)
        self.prompt = cfg.get("prompt") or "Transcribe this audio."

    def transcribe(self, path) -> str:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        resp = self.client.chat.completions.create(
            model=self.model, temperature=0,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": self.prompt},
                {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
            ]}])
        return (resp.choices[0].message.content or "").strip()
