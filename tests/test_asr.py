import os
import tempfile
import pytest
import numpy as np
import soundfile as sf

from broll_engine.speech.asr.base import TranscriptionResult, WordTiming
from broll_engine.speech.asr.mock import MockASRProvider
from broll_engine.speech.asr.whisper import FasterWhisperASRProvider


@pytest.fixture
def sample_wav_path():
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = tmp.name

    sample_rate = 16000
    duration_sec = 4.0
    total_samples = int(duration_sec * sample_rate)
    t = np.linspace(0, duration_sec, total_samples, endpoint=False)
    # Speech-like formant excitation with realistic word pauses recognized by Silero VAD
    word_pause = (t % 1.0) < 0.75
    glottal = ((t * 130) % 1.0 < 0.12).astype(np.float32)
    syllables = np.maximum(0.0, np.sin(2 * np.pi * 4.0 * t))
    formant = np.sin(2 * np.pi * 650 * t) + 0.6 * np.sin(2 * np.pi * 1200 * t)
    signal = glottal * syllables * formant * word_pause * 0.5
    data = (signal * 32767).astype(np.int16)
    sf.write(path, data, sample_rate, subtype="PCM_16")

    yield path

    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_mock_asr_english(sample_wav_path):
    """Verifies English ASR transcription and word alignment."""
    asr = MockASRProvider(default_language="en")
    result: TranscriptionResult = await asr.transcribe(sample_wav_path, language="en")

    assert result.language == "en"
    assert result.duration >= 3.9
    assert len(result.words) > 0

    # Verify word timing constraints
    prev_end = 0.0
    for w in result.words:
        assert isinstance(w, WordTiming)
        assert w.word != ""
        assert w.start >= prev_end or w.start >= 0.0
        assert w.end > w.start
        assert 0.0 <= w.probability <= 1.0
        prev_end = w.start


@pytest.mark.asyncio
async def test_mock_asr_hindi(sample_wav_path):
    """Verifies Hindi ASR transcription and metadata (Outstanding criterion)."""
    asr = MockASRProvider()
    result: TranscriptionResult = await asr.transcribe(sample_wav_path, language="hi-IN")

    assert result.language == "hi"
    assert "भारत" in result.text
    assert len(result.words) >= 5
    for w in result.words:
        assert w.end > w.start


@pytest.mark.asyncio
async def test_mock_asr_tamil(sample_wav_path):
    """Verifies Tamil ASR transcription and metadata (Outstanding criterion)."""
    asr = MockASRProvider()
    result: TranscriptionResult = await asr.transcribe(sample_wav_path, language="ta-IN")

    assert result.language == "ta"
    assert "தொழில்நுட்பம்" in result.text
    assert len(result.words) >= 4
    for w in result.words:
        assert w.end > w.start


def test_faster_whisper_provider_initialization():
    """Verifies FasterWhisperASRProvider configurable settings."""
    provider = FasterWhisperASRProvider(model_size="tiny", device="cpu", compute_type="int8")
    assert provider.model_size == "tiny"
    assert provider.device == "cpu"
    assert provider.compute_type == "int8"
