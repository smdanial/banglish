from eval.romanizer import Romanizer, rules_romanize


def test_rules_romanize_examples():
    assert rules_romanize("কাল বিকাল চারটায় অফিসে মিটিং আছে।") == "kal bikal chartay ofise miting ache."
    assert rules_romanize("আমি পনেরোশো টাকা দিবো") == "ami ponerosho taka dibo"
    assert rules_romanize("০১৭১২ ok") == "01712 ok"


class _FakeLLM:
    calls = 0

    class chat:  # noqa: N801
        class completions:  # noqa: N801
            @staticmethod
            def create(**kw):
                _FakeLLM.calls += 1
                msg = type("M", (), {"content": "ami"})
                return type("R", (), {"choices": [type("C", (), {"message": msg})]})


def test_latin_text_untouched_and_llm_cached(tmp_path, monkeypatch):
    import eval.models.openai_compat as oc
    monkeypatch.setattr(oc, "make_client", lambda cfg: (_FakeLLM, "fake-model", None))
    r = Romanizer({"method": "llm", "prompt": "p"}, {}, tmp_path)
    assert r.label == "llm:fake-model"
    assert r("ami kal jabo") == "ami kal jabo" and _FakeLLM.calls == 0
    assert r("আমি") == "ami" and _FakeLLM.calls == 1
    r2 = Romanizer({"method": "llm", "prompt": "p"}, {}, tmp_path)
    assert r2("আমি") == "ami" and _FakeLLM.calls == 1  # served from the disk cache


def test_llm_without_key_falls_back_and_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = Romanizer({"method": "llm", "fallback": "rules"}, {"api_key_env": "GEMINI_API_KEY",
                                                           "default_model": "m"}, tmp_path)
    assert r.label == "rules" and "unavailable" in r.note
    r = Romanizer({"method": "llm", "fallback": None}, {"api_key_env": "GEMINI_API_KEY",
                                                        "default_model": "m"}, tmp_path)
    assert not r.available


def test_devanagari_output_is_romanized_too():
    # Whisper with language="bn" sometimes writes Devanagari instead of Bengali script.
    assert rules_romanize("आज दूपुरे भात खाबो") == "aj dupure bhat khabo"


def test_stray_nukta_and_vowel_signs():
    assert rules_romanize("भाज़े") == "bhaje"
    assert rules_romanize("জেো") == "jeo"
