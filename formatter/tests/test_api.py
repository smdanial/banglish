import pytest

from banglish_formatter import MATCH_THRESHOLD, format_note

KEYS = {"type", "result", "confidence", "matched", "notes"}


@pytest.mark.parametrize("text", ["akash er sathe meeting ache bikal 4 tay", "alu 50 tk, piyaj 40 tk", "ami bhalo achi", ""])
def test_shape(text):
    out = format_note(text)
    assert set(out) == KEYS
    assert out["type"] in {"schedule", "expenses", "other"}
    assert isinstance(out["result"], str) and isinstance(out["notes"], str)
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["matched"] is (out["type"] != "other")
    assert out["matched"] is (out["confidence"] >= MATCH_THRESHOLD)


def test_rejects_non_string():
    with pytest.raises(TypeError):
        format_note(None)


def test_vocab_yaml_rejects_unquoted_booleans(tmp_path, monkeypatch):
    import shutil

    from banglish_formatter import vocab

    for name in ("numbers.yaml", "lexicon.yaml"):
        shutil.copy(vocab.DATA_DIR / name, tmp_path / name)
    text = (tmp_path / "numbers.yaml").read_text(encoding="utf-8").replace("words:\n", "words:\n  no: 1\n", 1)
    (tmp_path / "numbers.yaml").write_text(text, encoding="utf-8")
    monkeypatch.setattr(vocab, "DATA_DIR", tmp_path)
    vocab.get_vocab.cache_clear()
    try:
        with pytest.raises(ValueError, match="quoted"):
            vocab.get_vocab()
    finally:
        vocab.get_vocab.cache_clear()
