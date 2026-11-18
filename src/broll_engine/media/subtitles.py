"""Subtitles generation, formatting, and burn-in styling engine (Phase 5)."""

from pathlib import Path
from typing import Dict, List, Optional
from broll_engine.logging import get_logger
from broll_engine.models.scenes import Scene

logger = get_logger(__name__)


def format_srt_timestamp(seconds: float) -> str:
    """Formats floating-point seconds into standard SRT timecode: HH:MM:SS,mmm."""
    sec = max(0.0, float(seconds))
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    secs = int(sec % 60)
    millis = int(round((sec - int(sec)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_ass_timestamp(seconds: float) -> str:
    """Formats floating-point seconds into standard ASS timecode: H:MM:SS.cc."""
    sec = max(0.0, float(seconds))
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    secs = int(sec % 60)
    centis = int(round((sec - int(sec)) * 100))
    if centis >= 100:
        secs += 1
        centis -= 100
    return f"{hours:1d}:{minutes:02d}:{secs:02d}.{centis:02d}"


class SubtitleGenerator:
    """Generates standardized SRT and styled ASS subtitles from scenes and word timings."""

    def generate_srt_from_scenes(self, scenes: List[Scene]) -> str:
        """Constructs valid SRT subtitle file content from segmented scenes."""
        entries = []
        for i, scene in enumerate(scenes, start=1):
            start_tc = format_srt_timestamp(scene.start_seconds)
            end_tc = format_srt_timestamp(scene.end_seconds)
            text = scene.narration_text.strip()
            entries.append(f"{i}\n{start_tc} --> {end_tc}\n{text}\n")
        return "\n".join(entries).strip() + "\n"

    def generate_srt_from_words(self, words: List[Dict[str, any]], max_words_per_line: int = 7) -> str:
        """Constructs pacing-optimized SRT from word-level timestamps."""
        if not words:
            return ""

        chunks = []
        current_chunk = []
        for w in words:
            current_chunk.append(w)
            # Break chunk if reaches max words or word ends with sentence punctuation
            text = str(w.get("word", "")).strip()
            if len(current_chunk) >= max_words_per_line or text.endswith((".", "!", "?", "।")):
                chunks.append(current_chunk)
                current_chunk = []
        if current_chunk:
            chunks.append(current_chunk)

        entries = []
        for idx, chunk in enumerate(chunks, start=1):
            start_time = float(chunk[0].get("start", 0.0))
            end_time = float(chunk[-1].get("end", start_time + 1.0))
            line_text = " ".join(str(w.get("word", "")).strip() for w in chunk)
            start_tc = format_srt_timestamp(start_time)
            end_tc = format_srt_timestamp(end_time)
            entries.append(f"{idx}\n{start_tc} --> {end_tc}\n{line_text}\n")

        return "\n".join(entries).strip() + "\n"

    def write_srt_file(self, content: str, target_path: str) -> str:
        """Writes SRT content to target file path."""
        p = Path(target_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def generate_ass_content(
        self,
        scenes: List[Scene],
        font_size: int = 22,
        primary_color: str = "&H00FFFFFF",  # White
        outline_color: str = "&H00000000",  # Black
        outline_width: int = 2,
        margin_v: int = 45,
    ) -> str:
        """Generates Advanced SubStation Alpha (.ass) format with crisp broadcast typography."""
        header = f"""[Script Info]
Title: IncuBrix B-Roll Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline_width},1,2,20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for scene in scenes:
            start_tc = format_ass_timestamp(scene.start_seconds)
            end_tc = format_ass_timestamp(scene.end_seconds)
            text = scene.narration_text.strip().replace("\n", " ")
            events.append(f"Dialogue: 0,{start_tc},{end_tc},Default,,0,0,0,,{text}")

        return header + "\n".join(events) + "\n"
