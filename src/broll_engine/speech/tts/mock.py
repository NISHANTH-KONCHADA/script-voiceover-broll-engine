import os
import tempfile
import numpy as np
import scipy.io.wavfile as wavfile
from typing import List, Optional

from broll_engine.speech.asr.base import WordTiming
from broll_engine.speech.tts.base import TTSMetadata, TTSProvider, TTSResult
from broll_engine.speech.tts.edge import resolve_voice


class MockTTSProvider(TTSProvider):
    """
    Deterministic offline TTS provider generating synthetic WAV audio with exact word alignments.
    Enables offline continuous integration with zero network dependency.
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> TTSResult:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text.")

        resolved_voice = resolve_voice(voice)
        words_list = clean_text.split()
        num_words = len(words_list)

        # Estimate duration: average speaking rate ~ 2.5 words per second
        # Minimum 1.0s, with a lead-in and pad
        word_duration = 0.35
        gap_duration = 0.05
        lead_in = 0.1
        duration_seconds = max(1.0, lead_in + (num_words * (word_duration + gap_duration)) + 0.2)

        # Generate audio signal (modulated harmonic tone resembling speech envelope)
        total_samples = int(duration_seconds * self.sample_rate)
        t = np.linspace(0, duration_seconds, total_samples, endpoint=False)

        # Formant-like carrier frequencies (220Hz and 440Hz) with gentle speech-like envelope
        carrier = 0.6 * np.sin(2 * np.pi * 220 * t) + 0.4 * np.sin(2 * np.pi * 440 * t)

        # Apply burst envelope over word intervals
        envelope = np.zeros(total_samples, dtype=np.float32)
        words: List[WordTiming] = []
        current_t = lead_in

        for w in words_list:
            start_t = current_t
            # Duration slightly scaled by word length
            w_dur = max(0.2, min(0.8, len(w) * 0.06))
            end_t = start_t + w_dur

            start_idx = int(start_t * self.sample_rate)
            end_idx = min(total_samples, int(end_t * self.sample_rate))
            if start_idx < end_idx:
                envelope[start_idx:end_idx] = 1.0

            words.append(
                WordTiming(
                    word=w,
                    start=round(start_t, 3),
                    end=round(end_t, 3),
                    probability=1.0,
                )
            )
            current_t = end_t + gap_duration

        # Modulated speech-like waveform
        audio_signal = carrier * envelope * 0.5  # -6 dBFS level
        audio_int16 = (audio_signal * 32767).astype(np.int16)

        if output_path is None:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            output_path = tmp.name
            tmp.close()

        wavfile.write(output_path, self.sample_rate, audio_int16)

        with open(output_path, "rb") as f:
            audio_bytes = f.read()

        voice_lang = "-".join(resolved_voice.split("-")[:2])
        metadata = TTSMetadata(
            voice=resolved_voice,
            language=voice_lang,
            duration_seconds=round(duration_seconds, 3),
            sample_rate=self.sample_rate,
            word_count=num_words,
        )

        return TTSResult(
            audio_path=output_path,
            audio_bytes=audio_bytes,
            words=words,
            metadata=metadata,
        )
