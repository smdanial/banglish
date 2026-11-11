"""Model adapters. Every adapter exposes .transcribe(path) -> str.

Add your own model without touching this file: write a Python file with a function
`transcribe(path) -> str` (and optionally `setup(options)`), then add to eval/config.yaml:
    - name: my-model
      type: plugin
      file: eval/plugins/my_model.py     # or  module: eval.plugins.my_model
      romanize: false                    # true if it outputs Bengali script
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path


class PluginModel:
    def __init__(self, cfg: dict, api_cfg: dict):
        fn_name = cfg.get("function", "transcribe")
        if cfg.get("file"):
            p = Path(cfg["file"]).resolve()
            spec = importlib.util.spec_from_file_location(f"eval_plugin_{p.stem}", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        elif cfg.get("module"):
            mod = importlib.import_module(cfg["module"])
        else:
            raise ValueError("plugin model needs 'file' or 'module'")
        if hasattr(mod, "setup"):
            mod.setup(cfg.get("options") or {})
        self._fn = getattr(mod, fn_name)

    def transcribe(self, path) -> str:
        return self._fn(str(path))


def check(cfg: dict, api_cfg: dict):
    """Return None if the model can run here, else a short reason to skip it."""
    t = cfg.get("type")
    if t == "faster_whisper":
        if importlib.util.find_spec("faster_whisper") is None:
            return "faster-whisper not installed (pip install -r eval/requirements.txt)"
        return None
    if t == "openai_compat":
        from .openai_compat import resolve
        return resolve({**api_cfg, **cfg})[3]
    if t == "plugin":
        if cfg.get("file") and not Path(cfg["file"]).exists():
            return f"plugin file not found: {cfg['file']}"
        if cfg.get("module") and importlib.util.find_spec(cfg["module"].split(".")[0]) is None:
            return f"plugin module not found: {cfg['module']}"
        return None
    return f"unknown model type '{t}'"


def load(cfg: dict, api_cfg: dict):
    t = cfg.get("type")
    if t == "faster_whisper":
        from .faster_whisper_model import FasterWhisperModel
        return FasterWhisperModel(cfg)
    if t == "openai_compat":
        from .openai_compat import OpenAICompatModel
        return OpenAICompatModel({**api_cfg, **cfg})
    if t == "plugin":
        return PluginModel(cfg, api_cfg)
    raise ValueError(f"unknown model type '{t}'")
