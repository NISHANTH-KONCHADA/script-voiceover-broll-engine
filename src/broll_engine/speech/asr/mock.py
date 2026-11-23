from typing import List, Optional
from broll_engine.speech.asr.base import (
    ASRProvider,
    TranscriptionResult,
    TranscriptionSegment,
    WordTiming,
)
from broll_engine.speech.preflight import AudioPreflightValidator


class MockASRProvider(ASRProvider):
    """
    Deterministic ASR provider for offline testing and continuous integration.
    Generates frame-accurate synthetic word alignments without downloading model weights.
    """

    def __init__(
        self,
        default_language: str = "en",
        predefined_text: Optional[str] = None,
    ) -> None:
        self.default_language = default_language
        self.predefined_text = predefined_text
        self.preflight = AudioPreflightValidator()

    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> TranscriptionResult:
        # Preflight validation first
        metadata = self.preflight.validate_file(audio_path)
        duration = metadata.duration_seconds
        lang = language or self.default_language

        # Text selection based on language if not predefined
        if self.predefined_text:
            text = self.predefined_text
        elif lang.startswith("hi"):
            text = "भारत में नवाचार और तकनीक का तेजी से विकास हो रहा है।"
        elif lang.startswith("ta"):
            text = "தொழில்நுட்பம் மற்றும் புதுமை வாழ்க்கையை மாற்றுகிறது."
        else:
            text = "Welcome to the IncuBrix script and voiceover video engine."

        raw_words = text.split()
        num_words = len(raw_words)
        total_chars = sum(len(w) for w in raw_words) or 1

        lead_in = 0.1
        lead_out = 0.1
        available_time = max(0.4, duration - lead_in - lead_out)
        inter_word_gap = min(0.04, available_time / (num_words * 4))
        speech_time = available_time - (num_words * inter_word_gap)

        words: List[WordTiming] = []
        current_time = lead_in

        for i, word in enumerate(raw_words):
            word_fraction = len(word) / total_chars
            word_dur = max(0.05, word_fraction * speech_time)
            start_t = current_time
            end_t = start_t + word_dur
            current_time = end_t + inter_word_gap

            words.append(
                WordTiming(
                    word=word,
                    start=round(start_t, 3),
                    end=round(end_t, 3),
                    probability=0.98,
                )
            )

        segment = TranscriptionSegment(
            id=0,
            text=text,
            start=words[0].start if words else 0.0,
            end=words[-1].end if words else duration,
            words=words,
        )

        return TranscriptionResult(
            text=text,
            language=lang.split("-")[0],
            language_probability=0.99,
            duration=duration,
            words=words,
            segments=[segment],
        )
