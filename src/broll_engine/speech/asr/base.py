from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WordTiming:
    """Frame-accurate timestamp metadata for an individual spoken word."""
    word: str
    start: float
    end: float
    probability: float = 1.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "probability": round(self.probability, 3),
        }


@dataclass
class TranscriptionSegment:
    """Sentence or phrase segment of transcribed audio."""
    id: int
    text: str
    start: float
    end: float
    words: List[WordTiming] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class TranscriptionResult:
    """Full speech-to-text result with word-level alignment and language detection."""
    text: str
    language: str
    language_probability: float
    duration: float
    words: List[WordTiming]
    segments: List[TranscriptionSegment]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "language": self.language,
            "language_probability": round(self.language_probability, 3),
            "duration": round(self.duration, 3),
            "word_count": len(self.words),
            "words": [w.to_dict() for w in self.words],
            "segments": [s.to_dict() for s in self.segments],
        }


class ASRProvider(ABC):
    """Abstract interface for speech-to-text recognition engines."""

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> TranscriptionResult:
        """Transcribes audio file to text with word-level timing alignments.

        task: 'transcribe' (same-language) or 'translate' (to English).
        """
        pass
