import asyncio
from typing import Optional
from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.speech.asr.base import (
    ASRProvider,
    TranscriptionResult,
    TranscriptionSegment,
    WordTiming,
)

logger = get_logger(__name__)


class FasterWhisperASRProvider(ASRProvider):
    """Production ASR provider using CTranslate2-accelerated faster-whisper."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ) -> None:
        self.model_size = model_size or settings.whisper_model_size
        self.device = device or settings.whisper_device
        self.compute_type = compute_type or settings.whisper_compute_type
        self._model = None

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            logger.info(
                f"Loading faster-whisper model '{self.model_size}' on {self.device} ({self.compute_type})..."
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def _transcribe_sync(self, audio_path: str, language: Optional[str]) -> TranscriptionResult:
        model = self._get_model()

        # Normalize language codes (e.g., 'en-IN' -> 'en', 'hi-IN' -> 'hi', 'ta-IN' -> 'ta')
        lang_code = language.split("-")[0].lower() if language else None

        segments_gen, info = model.transcribe(
            audio_path,
            language=lang_code,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
        )

        all_words = []
        segments_list = []
        full_text_parts = []

        for seg_idx, segment in enumerate(segments_gen):
            full_text_parts.append(segment.text.strip())
            seg_words = []

            if segment.words:
                for w in segment.words:
                    word_timing = WordTiming(
                        word=w.word.strip(),
                        start=w.start,
                        end=w.end,
                        probability=w.probability,
                    )
                    all_words.append(word_timing)
                    seg_words.append(word_timing)

            segments_list.append(
                TranscriptionSegment(
                    id=seg_idx,
                    text=segment.text.strip(),
                    start=segment.start,
                    end=segment.end,
                    words=seg_words,
                )
            )

        full_text = " ".join(full_text_parts)
        return TranscriptionResult(
            text=full_text,
            language=info.language,
            language_probability=info.language_probability,
            duration=info.duration,
            words=all_words,
            segments=segments_list,
        )

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> TranscriptionResult:
        return await asyncio.to_thread(self._transcribe_sync, audio_path, language)
