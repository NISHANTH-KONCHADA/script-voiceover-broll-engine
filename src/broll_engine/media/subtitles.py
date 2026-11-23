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

    @staticmethod
    def extract_infographic_stat(text: str) -> Optional[str]:
        """Detects if narration mentions concrete data/statistics/metrics requiring an infographic callout."""
        import re
        lower = text.lower()

        # 1. Percentages: e.g. "99%", "50 percent"
        m_pct = re.search(r'(\d+(?:\.\d+)?)\s*(?:%|percent)', lower)
        if m_pct:
            return f"{m_pct.group(1)}% STATISTIC"

        # 2. Currency: e.g. "$100M", "$500"
        m_cur = re.search(r'\$(\d+(?:\.\d+)?\s*(?:[kKmMbB]|million|billion)?)', text)
        if m_cur:
            return f"${m_cur.group(1).upper()} METRIC"

        # 3. Billions / Millions / Calculations per second
        if "billion" in lower or "billions" in lower:
            if "per second" in lower or "every second" in lower:
                return "BILLIONS / SEC"
            return "1,000,000,000+ DATA"
        if "million" in lower or "millions" in lower:
            return "1,000,000+ SCALE"

        # 4. Multipliers: e.g. "10x", "5x faster"
        m_mult = re.search(r'(\d+(?:\.\d+)?x)', lower)
        if m_mult:
            return f"{m_mult.group(1).upper()} MULTIPLIER"

        # 5. Large numeric counts: e.g. "10,000" or "50,000"
        m_num = re.search(r'\b(\d{1,3}(?:,\d{3})+)\b', text)
        if m_num:
            return f"{m_num.group(1)} DATA"

        return None

    def generate_ass_content(
        self,
        scenes: List[Scene],
        font_name: str = "Inter",
        font_size: Optional[int] = None,
        primary_color: str = "&H00FFFFFF",  # White
        outline_color: str = "&H00000000",  # Black
        outline_width: int = 2,
        margin_v: Optional[int] = None,
        include_kinetic_titles: bool = True,
        all_caps_subtitles: bool = False,
        aspect_ratio: str = "16:9",
    ) -> str:
        """Generates Advanced SubStation Alpha (.ass) format with broadcast typography, reserving graphics strictly for data infographics."""
        # Calculate aspect-ratio specific canvas and safe-area margins
        aspect_norm = str(aspect_ratio).replace("x", ":")
        if aspect_norm == "9:16":
            play_res_x, play_res_y = 1080, 1920
            title_margin_v = 160  # Mobile top status bar safe zone
            sub_margin_v = margin_v if margin_v is not None else 210  # Mobile bottom UI safe zone
            title_fs = 44
            sub_fs = font_size if font_size is not None else 36
        elif aspect_norm == "1:1":
            play_res_x, play_res_y = 1080, 1080
            title_margin_v = 70
            sub_margin_v = margin_v if margin_v is not None else 95
            title_fs = 42
            sub_fs = font_size if font_size is not None else 36
        else:  # 16:9 landscape default
            play_res_x, play_res_y = 1920, 1080
            title_margin_v = 60
            sub_margin_v = margin_v if margin_v is not None else 85
            title_fs = 46
            sub_fs = font_size if font_size is not None else 42

        header = f"""[Script Info]
Title: IncuBrix HyperFrames Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{font_name},{title_fs},&H00FFFFFF,&H000000FF,&H30000000,&H80000000,-1,0,0,0,100,100,3,0,1,1,2,8,40,40,{title_margin_v},1
Style: Default,{font_name},{sub_fs},{primary_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,1,0,1,{outline_width},2,2,40,40,{sub_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for scene in scenes:
            start_tc = format_ass_timestamp(scene.start_seconds)
            end_tc = format_ass_timestamp(scene.end_seconds)
            text = scene.narration_text.strip().replace("\n", " ")

            # Only render animated infographic callouts when scene text contains concrete data/metrics
            if include_kinetic_titles:
                stat_metric = self.extract_infographic_stat(scene.narration_text)
                if stat_metric:
                    title_end_sec = min(scene.start_seconds + 3.0, scene.end_seconds)
                    title_start_tc = format_ass_timestamp(max(0.0, scene.start_seconds + 0.1))
                    title_end_tc = format_ass_timestamp(title_end_sec)

                    stat_line = (
                        f"Dialogue: 1,{title_start_tc},{title_end_tc},Title,,0,0,0,,"
                        f"{{\\fad(300,300)}}{{\\fs15\\c&H00A0A0A0&\\fsp3}}DATA METRIC\\N"
                        f"{{\\rTitle}}{{\\fs{title_fs}\\b1\\fsp3}}{stat_metric}"
                    )
                    events.append(stat_line)

            # Subtitle narration line
            final_text = text.upper() if all_caps_subtitles else text
            events.append(f"Dialogue: 0,{start_tc},{end_tc},Default,,0,0,0,,{final_text}")

        return header + "\n".join(events) + "\n"
