import copy
from typing import List, Tuple
from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.models.scenes import PacingStatus, Scene, SegmentationReason
from broll_engine.speech.asr.base import WordTiming

logger = get_logger(__name__)

SPLIT_CONJUNCTIONS = {
    # English conjunctions and prepositions
    "and", "but", "or", "so", "while", "because", "although", "though", "whereas",
    "however", "therefore", "furthermore", "which", "where", "when", "after", "before", "with",
    # Hindi conjunctions
    "और", "लेकिन", "किंतु", "परंतु", "जबकि", "क्योंकि", "इसलिए", "अतः",
    # Tamil conjunctions
    "மற்றும்", "ஆனால்", "எனவே", "ஆகையால்", "பிறகு", "முன்பு",
}


class PacingGuard:
    """
    Validates and enforces video pacing constraints across candidate scenes:
    - Minimum scene duration: 1.8s (prevents jarring, micro-flashes)
    - Maximum scene duration: 5.0s (prevents static, dragging visuals)
    - Zero gaps and zero overlaps (guarantees continuous narration coverage)
    """

    def __init__(
        self,
        min_duration_seconds: float = settings.min_scene_duration_seconds,
        max_duration_seconds: float = settings.max_scene_duration_seconds,
    ) -> None:
        self.min_duration = min_duration_seconds
        self.max_duration = max_duration_seconds

    def enforce_pacing(
        self,
        candidate_scenes: List[Scene],
        total_audio_duration: float,
    ) -> List[Scene]:
        """
        Executes two-pass pacing enforcement:
        Pass 1: Split excessively long scenes (> max_duration).
        Pass 2: Merge excessively short scenes (< min_duration).
        Pass 3: Normalize boundaries for gapless, continuous timeline coverage.
        """
        if not candidate_scenes:
            return []

        # Pass 1: Split scenes exceeding max_duration (5.0s)
        split_scenes: List[Scene] = []
        for sc in candidate_scenes:
            if sc.duration_seconds > self.max_duration:
                sub_scenes = self._split_scene(sc)
                split_scenes.extend(sub_scenes)
            else:
                split_scenes.append(sc)

        # Pass 2: Merge scenes shorter than min_duration (1.8s)
        merged_scenes = self._merge_short_scenes(split_scenes, total_audio_duration)

        # Pass 3: Gapless timeline normalization
        final_scenes = self._normalize_timeline(merged_scenes, total_audio_duration)

        return final_scenes

    def _split_scene(self, scene: Scene) -> List[Scene]:
        """
        Recursively or iteratively splits a scene exceeding max_duration at natural
        grammatical boundaries, silence gaps, or proportional word cuts.
        """
        if scene.duration_seconds <= self.max_duration or len(scene.words) <= 1:
            return [scene]

        # Calculate optimal number of parts
        num_parts = max(2, int(round(scene.duration_seconds / 3.0)))
        target_part_duration = scene.duration_seconds / float(num_parts)

        best_split_idx = -1
        best_score = float("inf")

        # Search for the best split point between index 1 and len-1
        for i in range(1, len(scene.words)):
            w_curr = scene.words[i - 1]
            w_next = scene.words[i]

            split_time = w_curr.end
            dur_left = split_time - scene.start_seconds
            dur_right = scene.end_seconds - split_time

            # Penalty for deviating from target_part_duration
            time_penalty = abs(dur_left - target_part_duration)

            # Bonus for natural punctuation
            punct_bonus = 0.0
            clean_word = w_curr.word.strip()
            if any(clean_word.endswith(p) for p in [",", ";", ".", "!", "?", "।", "—"]):
                punct_bonus -= 1.5

            # Bonus for conjunctions
            clean_token = re_clean(clean_word.lower())
            if clean_token in SPLIT_CONJUNCTIONS:
                punct_bonus -= 1.0

            # Bonus for silence gaps
            pause_dur = max(0.0, w_next.start - w_curr.end)
            if pause_dur >= 0.15:
                punct_bonus -= 1.2

            score = time_penalty + punct_bonus

            # Ensure both sides satisfy minimum duration if possible
            if dur_left >= 1.2 and dur_right >= 1.2:
                if score < best_score:
                    best_score = score
                    best_split_idx = i

        # Fallback to middle word if no grammatical break was found
        if best_split_idx == -1:
            best_split_idx = len(scene.words) // 2

        words_left = scene.words[:best_split_idx]
        words_right = scene.words[best_split_idx:]

        split_t = round(words_left[-1].end, 3)

        left_text = " ".join(w.word for w in words_left).strip()
        right_text = " ".join(w.word for w in words_right).strip()

        left_scene = copy.deepcopy(scene)
        left_scene.end_seconds = split_t
        left_scene.duration_seconds = round(split_t - left_scene.start_seconds, 3)
        left_scene.narration_text = left_text
        left_scene.words = words_left
        left_scene.segmentation_reason = SegmentationReason.PACING_SPLIT_MAX_DURATION
        left_scene.pacing_status = PacingStatus.SPLIT_OVER_MAX

        right_scene = copy.deepcopy(scene)
        right_scene.start_seconds = split_t
        right_scene.duration_seconds = round(right_scene.end_seconds - split_t, 3)
        right_scene.narration_text = right_text
        right_scene.words = words_right
        right_scene.segmentation_reason = SegmentationReason.PACING_SPLIT_MAX_DURATION
        right_scene.pacing_status = PacingStatus.SPLIT_OVER_MAX

        result = []
        # Recurse if any child part still exceeds max_duration
        if left_scene.duration_seconds > self.max_duration and len(left_scene.words) > 1:
            result.extend(self._split_scene(left_scene))
        else:
            result.append(left_scene)

        if right_scene.duration_seconds > self.max_duration and len(right_scene.words) > 1:
            result.extend(self._split_scene(right_scene))
        else:
            result.append(right_scene)

        return result

    def _merge_short_scenes(self, scenes: List[Scene], total_audio_duration: float) -> List[Scene]:
        """
        Merges scenes shorter than min_duration (< 1.8s) with appropriate neighbors.
        """
        if len(scenes) <= 1:
            return scenes

        merged: List[Scene] = []
        i = 0
        while i < len(scenes):
            curr = scenes[i]

            # If current scene is too short
            if curr.duration_seconds < self.min_duration:
                # If there's an existing merged scene before this one, merge backward
                if merged:
                    prev = merged[-1]
                    # Check if merging with prev keeps it reasonable
                    prev.end_seconds = curr.end_seconds
                    prev.duration_seconds = round(prev.end_seconds - prev.start_seconds, 3)
                    prev.narration_text = f"{prev.narration_text} {curr.narration_text}".strip()
                    prev.words.extend(curr.words)
                    prev.pacing_status = PacingStatus.MERGED_UNDER_MIN
                    prev.segmentation_reason = SegmentationReason.PACING_MERGE_MIN_DURATION
                    i += 1
                    continue
                # If it's the very first scene and there are subsequent scenes, merge forward
                elif i + 1 < len(scenes):
                    next_sc = scenes[i + 1]
                    next_sc.start_seconds = curr.start_seconds
                    next_sc.duration_seconds = round(next_sc.end_seconds - next_sc.start_seconds, 3)
                    next_sc.narration_text = f"{curr.narration_text} {next_sc.narration_text}".strip()
                    next_sc.words = curr.words + next_sc.words
                    next_sc.pacing_status = PacingStatus.MERGED_UNDER_MIN
                    next_sc.segmentation_reason = SegmentationReason.PACING_MERGE_MIN_DURATION
                    # Do not append curr, proceed to next
                    i += 1
                    continue

            merged.append(curr)
            i += 1

        # Check the last scene again: if it became shorter than min_duration
        if len(merged) > 1 and merged[-1].duration_seconds < self.min_duration:
            last = merged.pop()
            prev = merged[-1]
            prev.end_seconds = last.end_seconds
            prev.duration_seconds = round(prev.end_seconds - prev.start_seconds, 3)
            prev.narration_text = f"{prev.narration_text} {last.narration_text}".strip()
            prev.words.extend(last.words)
            prev.pacing_status = PacingStatus.MERGED_UNDER_MIN

        return merged

    def _normalize_timeline(self, scenes: List[Scene], total_audio_duration: float) -> List[Scene]:
        """
        Enforces strict contiguous timeline coverage:
        start_0 = 0.0
        start_i = end_{i-1}
        end_last = total_audio_duration
        duration_i = end_i - start_i
        """
        if not scenes:
            return []

        normalized: List[Scene] = []
        current_time = 0.0

        for idx, sc in enumerate(scenes):
            sc_norm = copy.deepcopy(sc)
            sc_norm.index = idx
            sc_norm.id = f"scene_{idx + 1:03d}"
            sc_norm.start_seconds = round(current_time, 3)

            # For the final scene, stretch or cap to the exact audio duration
            if idx == len(scenes) - 1:
                sc_norm.end_seconds = round(max(current_time + 0.1, total_audio_duration), 3)
            else:
                # Ensure end is strictly greater than start
                end_t = max(current_time + 0.5, sc_norm.end_seconds)
                sc_norm.end_seconds = round(end_t, 3)

            sc_norm.duration_seconds = round(sc_norm.end_seconds - sc_norm.start_seconds, 3)
            current_time = sc_norm.end_seconds
            normalized.append(sc_norm)

        return normalized


def re_clean(token: str) -> str:
    """Strips common punctuation from word for dictionary lookup."""
    return "".join(c for c in token if c.isalnum() or c in ("-", "_"))
