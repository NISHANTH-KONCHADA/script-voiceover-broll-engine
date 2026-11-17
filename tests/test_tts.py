import os
import tempfile
import pytest

from broll_engine.speech.preflight import AudioPreflightValidator
from broll_engine.speech.tts.base import TTSResult
from broll_engine.speech.tts.edge import EdgeTTSProvider, resolve_voice
from broll_engine.speech.tts.mock import MockTTSProvider


@pytest.mark.asyncio
async def test_mock_tts_english():
    """Verifies English narration synthesis with word timings."""
    tts = MockTTSProvider()
    text = "IncuBrix turns voiceovers and scripts into finished videos."
    result: TTSResult = await tts.synthesize(text, voice="en-IN-female")

    assert os.path.exists(result.audio_path)
    assert len(result.audio_bytes) > 0
    assert result.metadata.word_count == 8
    assert result.metadata.language == "en-IN"
    assert result.metadata.duration_seconds > 1.0
    assert len(result.words) == 8

    # Verify generated audio passes preflight validation
    validator = AudioPreflightValidator()
    meta = validator.validate_file(result.audio_path)
    assert meta.speech_ratio > 0.0

    # Clean up
    if os.path.exists(result.audio_path):
        os.remove(result.audio_path)


@pytest.mark.asyncio
async def test_mock_tts_hindi():
    """Verifies Hindi narration synthesis (Outstanding criterion)."""
    tts = MockTTSProvider()
    text = "यह एक स्वचालित वीडियो निर्माण प्रणाली है।"
    result: TTSResult = await tts.synthesize(text, voice="hi-IN-female")

    assert result.metadata.language == "hi-IN"
    assert result.metadata.voice == "hi-IN-SwaraNeural"
    assert len(result.words) == 7

    if os.path.exists(result.audio_path):
        os.remove(result.audio_path)


@pytest.mark.asyncio
async def test_mock_tts_tamil():
    """Verifies Tamil narration synthesis (Outstanding criterion)."""
    tts = MockTTSProvider()
    text = "இது ஒரு தானியங்கி வீடியோ இயந்திரம்."
    result: TTSResult = await tts.synthesize(text, voice="ta-IN-female")

    assert result.metadata.language == "ta-IN"
    assert result.metadata.voice == "ta-IN-PallaviNeural"
    assert len(result.words) == 5

    if os.path.exists(result.audio_path):
        os.remove(result.audio_path)


def test_voice_resolution():
    """Verifies voice alias resolution across English, Hindi, and Tamil."""
    assert resolve_voice("en-IN-female") == "en-IN-NeerjaNeural"
    assert resolve_voice("en-IN-male") == "en-IN-PrabhatNeural"
    assert resolve_voice("hi-IN-female") == "hi-IN-SwaraNeural"
    assert resolve_voice("hi-IN-male") == "hi-IN-MadhurNeural"
    assert resolve_voice("ta-IN-female") == "ta-IN-PallaviNeural"
    assert resolve_voice("ta-IN-male") == "ta-IN-ValluvarNeural"
    assert resolve_voice("en-US-female") == "en-US-JennyNeural"
    assert resolve_voice("en-US-male") == "en-US-GuyNeural"
    # Custom / direct voice
    assert resolve_voice("fr-FR-DeniseNeural") == "fr-FR-DeniseNeural"


@pytest.mark.asyncio
async def test_empty_text_raises_value_error():
    """Verifies synthesizing empty string raises ValueError."""
    tts = MockTTSProvider()
    with pytest.raises(ValueError):
        await tts.synthesize("   ")
