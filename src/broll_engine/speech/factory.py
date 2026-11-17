from typing import Optional
from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.speech.asr.base import ASRProvider
from broll_engine.speech.asr.mock import MockASRProvider
from broll_engine.speech.asr.whisper import FasterWhisperASRProvider
from broll_engine.speech.tts.base import TTSProvider
from broll_engine.speech.tts.edge import EdgeTTSProvider
from broll_engine.speech.tts.mock import MockTTSProvider

logger = get_logger(__name__)


def create_asr_provider(provider_type: Optional[str] = None) -> ASRProvider:
    """Instantiates ASR provider based on configuration or override."""
    ptype = (provider_type or settings.asr_provider).lower()
    if ptype in ("faster-whisper", "whisper"):
        logger.info(f"Instantiating FasterWhisperASRProvider ({settings.whisper_model_size})")
        return FasterWhisperASRProvider()
    elif ptype == "mock":
        logger.info("Instantiating MockASRProvider")
        return MockASRProvider()
    else:
        raise ValueError(f"Unknown ASR provider: {ptype}. Supported: faster-whisper, mock")


def create_tts_provider(provider_type: Optional[str] = None) -> TTSProvider:
    """Instantiates TTS provider based on configuration or override."""
    ptype = (provider_type or settings.tts_provider).lower()
    if ptype in ("edge-tts", "edge"):
        logger.info("Instantiating EdgeTTSProvider")
        return EdgeTTSProvider()
    elif ptype == "mock":
        logger.info("Instantiating MockTTSProvider")
        return MockTTSProvider()
    else:
        raise ValueError(f"Unknown TTS provider: {ptype}. Supported: edge-tts, mock")
