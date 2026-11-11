"""Template for adding a new model. Copy this file, change transcribe(), and add an entry
to eval/config.yaml (see the disabled 'example-plugin' entry there).

transcribe(path) gets the full path to a 16 kHz mono WAV file and must return the text.
setup(options) is optional; it runs once before the first file, with `options:` from config.yaml.
"""

_reply = ""


def setup(options: dict) -> None:
    global _reply
    _reply = options.get("reply", "")


def transcribe(path: str) -> str:
    # Replace this with a call to your model. This dummy always returns the same text.
    return _reply
