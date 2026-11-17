from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from broll_engine.speech.asr.base import WordTiming


@dataclass
class TTSMetadata:
    """Provenance and audio facts for synthesized narration."""
    voice: str
    language: str
    duration_seconds: float
    sample_rate: int
    word_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "voice": self.voice,
            "language": self.language,
            "duration_seconds": round(self.duration_seconds, 3),
            "sample_rate": self.sample_rate,
            "word_count": self.word_count,
        }


@dataclass
class TTSResult:
    """Output from text-to-speech synthesis containing audio file and word timings."""
    audio_path: str
    audio_bytes: bytes
    words: List[WordTiming]
    metadata: TTSMetadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audio_path": self.audio_path,
            "words": [w.to_dict() for w in self.words],
            "metadata": self.metadata.to_dict(),
        }


class TTSProvider(ABC):
    """Abstract interface for text-to-speech narration synthesis engines."""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> TTSResult:
        """Synthesizes speech from text, emitting master audio and aligned word timestamps."""
        pass
