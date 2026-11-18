import os
import tempfile
import numpy as np
import pytest
import soundfile as sf

from broll_engine.speech.preflight import (
    AudioMetadata,
    AudioPreflightError,
    AudioPreflightValidator,
)


@pytest.fixture
def temp_audio_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


def create_synthetic_wav(path: str, duration_sec: float, sample_rate: int = 16000, silent: bool = False):
    """Creates a synthetic WAV file with voiced speech-like formants or pure silence."""
    total_samples = int(duration_sec * sample_rate)
    if silent:
        data = np.zeros(total_samples, dtype=np.int16)
    else:
        t = np.linspace(0, duration_sec, total_samples, endpoint=False)
        # Glottal excitation modulated by speech syllables and acoustic formants
        glottal = ((t * 130) % 1.0 < 0.1).astype(np.float32)
        syllables = np.maximum(0.0, np.sin(2 * np.pi * 3.5 * t))
        formant = np.sin(2 * np.pi * 700 * t) + 0.5 * np.sin(2 * np.pi * 1220 * t)
        sig = glottal * syllables * formant * 0.5
        data = (sig * 32767).astype(np.int16)
    sf.write(path, data, sample_rate, subtype="PCM_16")


def test_valid_wav_passes_preflight(temp_audio_dir):
    """Verifies that standard valid WAV audio passes all checks."""
    path = os.path.join(temp_audio_dir, "speech.wav")
    create_synthetic_wav(path, duration_sec=3.0, silent=False)

    validator = AudioPreflightValidator()
    meta = validator.validate_file(path)

    assert isinstance(meta, AudioMetadata)
    assert meta.format == "wav"
    assert 2.9 <= meta.duration_seconds <= 3.1
    assert meta.sample_rate == 16000
    assert meta.channels == 1
    assert meta.rms_dbfs > -30.0
    assert meta.speech_ratio > 0.5


def test_unsupported_format_rejected(temp_audio_dir):
    """Verifies that unsupported formats (e.g. .flac, .ogg, .txt) are rejected."""
    path = os.path.join(temp_audio_dir, "audio.flac")
    with open(path, "wb") as f:
        f.write(b"NOT_A_VALID_FORMAT")

    validator = AudioPreflightValidator()
    with pytest.raises(AudioPreflightError) as exc_info:
        validator.validate_file(path)

    assert exc_info.value.code == "UNSUPPORTED_AUDIO_FORMAT"


def test_nonexistent_file_rejected(temp_audio_dir):
    """Verifies missing file raises AUDIO_FILE_NOT_FOUND."""
    path = os.path.join(temp_audio_dir, "does_not_exist.mp3")
    validator = AudioPreflightValidator()
    with pytest.raises(AudioPreflightError) as exc_info:
        validator.validate_file(path)

    assert exc_info.value.code == "AUDIO_FILE_NOT_FOUND"


def test_corrupted_file_rejected(temp_audio_dir):
    """Verifies unreadable bytes in a .wav file raises CORRUPTED_AUDIO_FILE."""
    path = os.path.join(temp_audio_dir, "corrupt.wav")
    with open(path, "wb") as f:
        f.write(b"RIFF\x00\x00\x00\x00WAVEfmt garbage corrupt bytes")

    validator = AudioPreflightValidator()
    with pytest.raises(AudioPreflightError) as exc_info:
        validator.validate_file(path)

    assert exc_info.value.code == "CORRUPTED_AUDIO_FILE"


def test_duration_exceeding_10_minutes_rejected(temp_audio_dir):
    """Verifies duration limit (> 600s) raises AUDIO_EXCEEDS_MAX_DURATION."""
    path = os.path.join(temp_audio_dir, "long.wav")
    # Simulate a file exceeding 10 minutes (601 seconds) using custom max_duration
    create_synthetic_wav(path, duration_sec=5.0, silent=False)

    validator = AudioPreflightValidator(max_duration_seconds=4.0)
    with pytest.raises(AudioPreflightError) as exc_info:
        validator.validate_file(path)

    assert exc_info.value.code == "AUDIO_EXCEEDS_MAX_DURATION"
    assert "exceeds" in exc_info.value.message


def test_duration_too_short_rejected(temp_audio_dir):
    """Verifies audio shorter than 0.5s raises AUDIO_TOO_SHORT."""
    path = os.path.join(temp_audio_dir, "short.wav")
    create_synthetic_wav(path, duration_sec=0.2, silent=False)

    validator = AudioPreflightValidator(min_duration_seconds=0.5)
    with pytest.raises(AudioPreflightError) as exc_info:
        validator.validate_file(path)

    assert exc_info.value.code == "AUDIO_TOO_SHORT"


def test_silent_audio_rejected(temp_audio_dir):
    """Verifies completely silent audio raises NO_SPEECH_DETECTED."""
    path = os.path.join(temp_audio_dir, "silent.wav")
    create_synthetic_wav(path, duration_sec=3.0, silent=True)

    validator = AudioPreflightValidator()
    with pytest.raises(AudioPreflightError) as exc_info:
        validator.validate_file(path)

    assert exc_info.value.code == "NO_SPEECH_DETECTED"


def test_silero_vad_rejects_pure_sine_tone(temp_audio_dir):
    """
    Verifies that Silero VAD as neural acoustic detector rejects pure sine tones
    as non-speech, even when loud, proving it is not just relying on simple RMS energy.
    """
    path = os.path.join(temp_audio_dir, "pure_tone.wav")
    total_samples = 16000 * 3
    t = np.linspace(0, 3.0, total_samples, endpoint=False)
    pure_tone = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    sf.write(path, pure_tone, 16000, subtype="PCM_16")

    validator = AudioPreflightValidator(vad_provider="silero")
    with pytest.raises(AudioPreflightError) as exc_info:
        validator.validate_file(path)

    assert exc_info.value.code == "NO_SPEECH_DETECTED"
    assert exc_info.value.details.get("vad_provider") == "silero"


def test_vad_energy_mode_fallback(temp_audio_dir):
    """Verifies that energy-based VAD mode functions correctly as a fallback."""
    path = os.path.join(temp_audio_dir, "speech_energy.wav")
    create_synthetic_wav(path, duration_sec=3.0, silent=False)

    validator = AudioPreflightValidator(vad_provider="energy")
    meta = validator.validate_file(path)

    assert meta.vad_provider == "energy"
    assert meta.speech_ratio > 0.0
