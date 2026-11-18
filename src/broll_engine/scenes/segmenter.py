import re
from typing import Any, Dict, List, Optional, Tuple
from broll_engine.api.schemas.job import SceneHint
from broll_engine.logging import get_logger
from broll_engine.models.scenes import (
    PacingStatus,
    Scene,
    SceneSegmentationResult,
    SegmentationReason,
    TimingSource,
)
from broll_engine.scenes.disambiguation import ContextualQueryDisambiguator
from broll_engine.scenes.pacing import PacingGuard
from broll_engine.speech.asr.base import WordTiming

logger = get_logger(__name__)

# Punctuation marks denoting sentence boundaries in English, Hindi, and Tamil
SENTENCE_END_PUNCTUATION = {".", "!", "?", "।"}


class SemanticSceneSegmenter:
    """
    Orchestrates semantic segmentation of narration audio into visual scenes:
    1. Sentence & grammatical clause boundary tokenization
    2. Alignment with word-level speech timestamps
    3. Pacing Guard enforcement (1.8s - 5.0s range, zero gaps/overlaps)
    4. Contextual query disambiguation, visual metaphor generation, and safety filters
    """

    def __init__(
        self,
        pacing_guard: Optional[PacingGuard] = None,
        disambiguator: Optional[ContextualQueryDisambiguator] = None,
    ) -> None:
        self.pacing = pacing_guard or PacingGuard()
        self.disambiguator = disambiguator or ContextualQueryDisambiguator()

    def segment(
        self,
        transcript_text: str,
        words: List[WordTiming],
        total_duration_seconds: float,
        language: str = "en",
        timing_source: TimingSource = TimingSource.ASR_ACOUSTIC,
        scenes_hint: Optional[List[SceneHint]] = None,
        style_hint: Optional[str] = None,
        user_avoid_list: Optional[List[str]] = None,
    ) -> SceneSegmentationResult:
        """
        Executes end-to-end scene segmentation.
        """
        clean_text = transcript_text.strip()
        if not clean_text or total_duration_seconds <= 0:
            return SceneSegmentationResult(
                scenes=[],
                total_duration_seconds=0.0,
                scene_count=0,
                timing_source=timing_source,
                has_gaps=False,
                has_overlaps=False,
                pacing_adherence_rate=1.0,
            )

        # Fallback if words list is empty (e.g. synthetic single phrase)
        if not words:
            raw_words = clean_text.split()
            word_dur = total_duration_seconds / max(1, len(raw_words))
            words = [
                WordTiming(
                    word=w,
                    start=round(i * word_dur, 3),
                    end=round((i + 1) * word_dur, 3),
                    probability=1.0,
                )
                for i, w in enumerate(raw_words)
            ]

        # Case 1: Pre-segmented director hints provided in request
        if scenes_hint and len(scenes_hint) > 0:
            raw_candidate_scenes = self._segment_from_director_hints(
                scenes_hint=scenes_hint,
                words=words,
                total_duration=total_duration_seconds,
                language=language,
                timing_source=timing_source,
            )
        else:
            # Case 2: Automatic semantic clause & sentence segmentation
            raw_candidate_scenes = self._segment_automatically(
                transcript_text=clean_text,
                words=words,
                total_duration=total_duration_seconds,
                language=language,
                timing_source=timing_source,
            )

        # Step 2: Enforce Pacing Guard (min 1.8s, max 5.0s, continuous timeline)
        paced_scenes = self.pacing.enforce_pacing(
            candidate_scenes=raw_candidate_scenes,
            total_audio_duration=total_duration_seconds,
        )

        # Step 3: Contextual Query Disambiguation & Safety Constraints
        for sc in paced_scenes:
            # Find matching visual hint if available
            matching_hint = None
            if scenes_hint and sc.index < len(scenes_hint):
                matching_hint = scenes_hint[sc.index].visual_hint

            v_query, v_intent, neg_constraints = self.disambiguator.disambiguate_scene(
                scene_text=sc.narration_text,
                full_context=clean_text,
                language=language,
                user_avoid_list=user_avoid_list,
                style_hint=style_hint,
                visual_hint=matching_hint,
            )
            sc.visual_query = v_query
            sc.visual_intent = v_intent
            sc.negative_constraints = neg_constraints

        # Step 4: Verification Metrics
        has_gaps, has_overlaps, adherence_rate = self._compute_metrics(paced_scenes, total_duration_seconds)

        return SceneSegmentationResult(
            scenes=paced_scenes,
            total_duration_seconds=round(total_duration_seconds, 3),
            scene_count=len(paced_scenes),
            timing_source=timing_source,
            has_gaps=has_gaps,
            has_overlaps=has_overlaps,
            pacing_adherence_rate=adherence_rate,
        )

    def _segment_automatically(
        self,
        transcript_text: str,
        words: List[WordTiming],
        total_duration: float,
        language: str,
        timing_source: TimingSource,
    ) -> List[Scene]:
        """
        Segments text into natural grammatical sentences and clauses,
        aligning them against the words list.
        """
        candidate_scenes: List[Scene] = []
        current_words: List[WordTiming] = []

        for w_idx, w in enumerate(words):
            current_words.append(w)
            clean_w = w.word.strip()

            is_last_word = (w_idx == len(words) - 1)
            ends_with_sentence_punct = any(clean_w.endswith(p) for p in SENTENCE_END_PUNCTUATION)

            # Check if this word terminates a sentence or clause
            if ends_with_sentence_punct or is_last_word:
                segment_text = " ".join(item.word for item in current_words).strip()
                start_t = round(current_words[0].start, 3)
                end_t = round(current_words[-1].end, 3)
                dur = round(max(0.1, end_t - start_t), 3)

                scene = Scene(
                    id=f"scene_{len(candidate_scenes) + 1:03d}",
                    index=len(candidate_scenes),
                    start_seconds=start_t,
                    end_seconds=end_t,
                    duration_seconds=dur,
                    narration_text=segment_text,
                    language=language,
                    visual_query=segment_text,  # Temporary, disambiguated in Step 3
                    segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
                    pacing_status=PacingStatus.VALID,
                    timing_source=timing_source,
                    words=list(current_words),
                )
                candidate_scenes.append(scene)
                current_words = []

        # If any trailing words remain
        if current_words:
            segment_text = " ".join(item.word for item in current_words).strip()
            start_t = round(current_words[0].start, 3)
            end_t = round(current_words[-1].end, 3)
            dur = round(max(0.1, end_t - start_t), 3)
            candidate_scenes.append(
                Scene(
                    id=f"scene_{len(candidate_scenes) + 1:03d}",
                    index=len(candidate_scenes),
                    start_seconds=start_t,
                    end_seconds=end_t,
                    duration_seconds=dur,
                    narration_text=segment_text,
                    language=language,
                    visual_query=segment_text,
                    segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
                    pacing_status=PacingStatus.VALID,
                    timing_source=timing_source,
                    words=list(current_words),
                )
            )

        return candidate_scenes

    def _segment_from_director_hints(
        self,
        scenes_hint: List[SceneHint],
        words: List[WordTiming],
        total_duration: float,
        language: str,
        timing_source: TimingSource,
    ) -> List[Scene]:
        """
        Maps user-supplied SceneHint objects to the word stream.
        """
        candidate_scenes: List[Scene] = []
        word_cursor = 0
        total_words_count = len(words)

        for h_idx, hint in enumerate(scenes_hint):
            hint_word_count = len(hint.text.strip().split())
            if h_idx == len(scenes_hint) - 1:
                # Last hint takes all remaining words
                slice_words = words[word_cursor:]
            else:
                end_cursor = min(total_words_count, word_cursor + max(1, hint_word_count))
                slice_words = words[word_cursor:end_cursor]
                word_cursor = end_cursor

            if not slice_words:
                slice_words = [words[-1]]

            start_t = round(slice_words[0].start, 3)
            end_t = round(slice_words[-1].end, 3)
            dur = round(max(0.1, end_t - start_t), 3)

            sc = Scene(
                id=f"scene_{h_idx + 1:03d}",
                index=h_idx,
                start_seconds=start_t,
                end_seconds=end_t,
                duration_seconds=dur,
                narration_text=hint.text.strip(),
                language=language,
                visual_query=hint.visual_hint or hint.text.strip(),
                segmentation_reason=SegmentationReason.DIRECTOR_HINT,
                pacing_status=PacingStatus.VALID,
                timing_source=timing_source,
                words=slice_words,
            )
            candidate_scenes.append(sc)

        return candidate_scenes

    def _compute_metrics(self, scenes: List[Scene], total_duration: float) -> Tuple[bool, bool, float]:
        """
        Evaluates timeline continuity and pacing adherence.
        Returns: (has_gaps, has_overlaps, adherence_rate)
        """
        if not scenes:
            return False, False, 1.0

        has_gaps = False
        has_overlaps = False
        adherent_count = 0

        for i in range(len(scenes)):
            sc = scenes[i]
            # Pacing adherence check (1.8s to 5.0s, allowing single short scene exception)
            if (self.pacing.min_duration <= sc.duration_seconds <= self.pacing.max_duration) or len(scenes) == 1:
                adherent_count += 1

            if i > 0:
                prev_sc = scenes[i - 1]
                delta = sc.start_seconds - prev_sc.end_seconds
                if delta > 0.05:
                    has_gaps = True
                elif delta < -0.05:
                    has_overlaps = True

        adherence_rate = round(float(adherent_count) / float(len(scenes)), 2)
        return has_gaps, has_overlaps, adherence_rate
