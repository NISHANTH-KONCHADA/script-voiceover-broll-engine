import os
import tempfile
from typing import Dict, List, Optional
import edge_tts
from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.speech.asr.base import WordTiming
from broll_engine.speech.preflight import AudioPreflightValidator
from broll_engine.speech.tts.base import TTSMetadata, TTSProvider, TTSResult

logger = get_logger(__name__)

VOICE_MAP: Dict[str, str] = {
    # Indian English
    "en-IN-female": "en-IN-NeerjaNeural",
    "en-IN-male": "en-IN-PrabhatNeural",
    "en-IN": "en-IN-NeerjaNeural",
    # US English
    "en-US-female": "en-US-JennyNeural",
    "en-US-male": "en-US-GuyNeural",
    "en-US": "en-US-JennyNeural",
    "en": "en-US-JennyNeural",
    # Hindi
    "hi-IN-female": "hi-IN-SwaraNeural",
    "hi-IN-male": "hi-IN-MadhurNeural",
    "hi-IN": "hi-IN-SwaraNeural",
    "hi": "hi-IN-SwaraNeural",
    # Tamil
    "ta-IN-female": "ta-IN-PallaviNeural",
    "ta-IN-male": "ta-IN-ValluvarNeural",
    "ta-IN": "ta-IN-PallaviNeural",
    "ta": "ta-IN-PallaviNeural",
}


def resolve_voice(voice: Optional[str]) -> str:
    """Resolves short voice alias or default to full neural voice identifier."""
    if not voice:
        return settings.default_voice_en_in
    if voice in VOICE_MAP:
        return VOICE_MAP[voice]
    # If already a full voice identifier (e.g. 'en-IN-NeerjaNeural'), return as is
    return voice


class EdgeTTSProvider(TTSProvider):
    """
    High-fidelity neural TTS provider using edge-tts.
    Extracts frame-accurate word boundary events and uncompressed audio.
    """

    def __init__(self) -> None:
        self.preflight = AudioPreflightValidator()

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
        logger.info(f"Synthesizing {len(clean_text.split())} words with voice '{resolved_voice}'")

        if output_path is None:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            output_path = tmp.name
            tmp.close()

        communicate = edge_tts.Communicate(clean_text, resolved_voice)

        words: List[WordTiming] = []
        audio_chunks: List[bytes] = []

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # offset and duration in 100ns ticks
                offset_sec = chunk["offset"] / 10_000_000.0
                duration_sec = chunk["duration"] / 10_000_000.0
                word_text = chunk["text"].strip()
                if word_text:
                    words.append(
                        WordTiming(
                            word=word_text,
                            start=round(offset_sec, 3),
                            end=round(offset_sec + duration_sec, 3),
                            probability=1.0,
                        )
                    )

        full_audio_bytes = b"".join(audio_chunks)
        with open(output_path, "wb") as f:
            f.write(full_audio_bytes)

        # Inspect duration and audio properties
        meta = self.preflight.validate_file(output_path)

        # Extract language prefix from voice (e.g. 'en-IN-NeerjaNeural' -> 'en-IN')
        voice_lang = "-".join(resolved_voice.split("-")[:2])

        metadata = TTSMetadata(
            voice=resolved_voice,
            language=voice_lang,
            duration_seconds=meta.duration_seconds,
            sample_rate=meta.sample_rate,
            word_count=len(words),
        )

        return TTSResult(
            audio_path=output_path,
            audio_bytes=full_audio_bytes,
            words=words,
            metadata=metadata,
        )
