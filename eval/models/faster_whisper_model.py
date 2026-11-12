from __future__ import annotations

AUTO = (None, "", "auto")


class FasterWhisperModel:
    """After each transcribe(), .last_info holds the language that was passed to faster-whisper, the one it
    decoded with, and the language Whisper itself detects in the audio (an extra detection pass when the
    language is forced; turn off with detect_language: false)."""

    def __init__(self, cfg: dict):
        from faster_whisper import WhisperModel
        lang = cfg.get("language", "bn")
        self.language = None if lang in AUTO else str(lang)
        self.initial_prompt = cfg.get("initial_prompt") or None
        self.detect = bool(cfg.get("detect_language", True))
        self.beam_size = int(cfg.get("beam_size", 5))
        self.last_info = None
        self.model = WhisperModel(cfg.get("size", "small"), device=cfg.get("device", "cpu"),
                                  compute_type=cfg.get("compute_type", "int8"),
                                  cpu_threads=int(cfg.get("cpu_threads", 0)))

    def describe(self) -> str:
        lang = f"language={self.language!r} (forced)" if self.language else "language=None (auto-detect)"
        prompt = f"initial_prompt={self.initial_prompt[:40]!r}..." if self.initial_prompt else "no initial_prompt"
        return f"faster-whisper {lang}, {prompt}"

    def transcribe(self, path) -> str:
        from faster_whisper import decode_audio
        audio = decode_audio(str(path), sampling_rate=self.model.feature_extractor.sampling_rate)
        self.last_info = None
        segments, info = self.model.transcribe(audio, language=self.language, beam_size=self.beam_size,
                                               initial_prompt=self.initial_prompt,
                                               vad_filter=False, condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        li = {"language_requested": self.language or "auto", "language_used": info.language}
        if self.language is None:
            li["language_detected"], li["language_detected_prob"] = info.language, round(info.language_probability, 3)
        elif self.detect:
            lang, prob, _ = self.model.detect_language(audio)
            li["language_detected"], li["language_detected_prob"] = lang, round(prob, 3)
        self.last_info = li
        return text
