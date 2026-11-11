from __future__ import annotations


class FasterWhisperModel:
    def __init__(self, cfg: dict):
        from faster_whisper import WhisperModel
        self.language = cfg.get("language", "bn")
        self.beam_size = int(cfg.get("beam_size", 5))
        self.model = WhisperModel(cfg.get("size", "small"), device=cfg.get("device", "cpu"),
                                  compute_type=cfg.get("compute_type", "int8"),
                                  cpu_threads=int(cfg.get("cpu_threads", 0)))

    def transcribe(self, path) -> str:
        segments, _ = self.model.transcribe(str(path), language=self.language, beam_size=self.beam_size,
                                            vad_filter=False, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()
