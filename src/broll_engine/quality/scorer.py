"""Scene-level and composite video quality scoring engine (Phase 6)."""

from typing import Dict, List, Optional, Tuple
from broll_engine.models.retrieval import SelectedClip
from broll_engine.models.scenes import Scene
from broll_engine.quality.models import (
    BlackFrameDetectionResult,
    FrozenFrameDetectionResult,
    SceneQualityScore,
    StreamValidationResult,
    SubtitleValidationResult,
    SyncValidationResult,
)


class QualityScorer:
    """Computes explainable per-scene quality scores and composite video quality metrics."""

    def score_scene(
        self,
        scene: Scene,
        clip: Optional[SelectedClip],
        used_clip_ids: Dict[str, int],
    ) -> SceneQualityScore:
        """Scores an individual scene on relevance, pacing, and visual diversity."""
        # 1. Relevance score (0.0 - 5.0 -> 0.0 - 100.0)
        raw_rel = clip.relevance_score if clip else 3.5
        relevance_100 = min(max(raw_rel * 20.0, 0.0), 100.0)

        # 2. Pacing score (duration in [1.8, 5.0])
        dur = scene.duration_seconds
        if 1.8 <= dur <= 5.0:
            pacing_score = 100.0
        elif 1.0 <= dur < 1.8:
            pacing_score = 75.0
        elif 5.0 < dur <= 7.0:
            pacing_score = 80.0
        else:
            pacing_score = 50.0

        # 3. Visual diversity score (penalize if clip asset_id was seen multiple times)
        clip_id = clip.asset_id if clip else "unknown"
        occurrences = used_clip_ids.get(clip_id, 1)
        if occurrences == 1:
            diversity_score = 100.0
        elif occurrences == 2:
            diversity_score = 40.0
        else:
            diversity_score = 10.0

        # Composite scene score
        composite = (
            0.40 * relevance_100
            + 0.35 * pacing_score
            + 0.25 * diversity_score
        )

        rationale = (
            f"Relevance: {raw_rel:.1f}/5.0 ({relevance_100:.0f}pts), "
            f"Pacing: {dur:.2f}s ({pacing_score:.0f}pts), "
            f"Diversity: {diversity_score:.0f}pts (occurrences: {occurrences})."
        )

        return SceneQualityScore(
            scene_id=scene.id,
            scene_index=scene.index,
            relevance_score=raw_rel,
            pacing_score=round(pacing_score, 1),
            visual_diversity_score=round(diversity_score, 1),
            composite_scene_score=round(composite, 1),
            rationale=rationale,
        )

    def compute_overall_quality(
        self,
        scene_scores: List[SceneQualityScore],
        stream_validation: StreamValidationResult,
        black_frames: BlackFrameDetectionResult,
        frozen_frames: FrozenFrameDetectionResult,
        sync_validation: SyncValidationResult,
        subtitle_validation: SubtitleValidationResult,
    ) -> Tuple[float, bool, List[str], List[str]]:
        """Calculates total composite score (0-100), pass/fail flag, warnings, and failures.

        Points Breakdown (100 total):
        - Objective broadcast compliance: 40 points
          * Codec & format validity: 15 pts
          * Zero black frames: 10 pts
          * Zero frozen frames: 5 pts
          * Zero audio drift: 10 pts
        - Scene quality & pacing: 60 points
          * Average scene composite score * 0.60
        """
        warnings: List[str] = []
        failures: List[str] = []

        # 1. Objective Broadcast Compliance (40 pts)
        objective_pts = 0.0

        # Streams check (15 pts)
        if stream_validation.is_valid_broadcast_format:
            objective_pts += 15.0
        else:
            failures.extend(stream_validation.issues)

        # Black frames check (10 pts)
        if not black_frames.detected or black_frames.total_black_duration < 0.10:
            objective_pts += 10.0
        else:
            failures.append(f"Black frames detected: {black_frames.total_black_duration:.2f}s total duration.")

        # Frozen frames check (5 pts)
        if not frozen_frames.detected or frozen_frames.total_frozen_duration < 0.50:
            objective_pts += 5.0
        else:
            warnings.append(f"Static/frozen frames detected: {frozen_frames.total_frozen_duration:.2f}s total duration.")

        # Audio synchronization check (10 pts)
        if sync_validation.within_tolerance:
            objective_pts += 10.0
        else:
            failures.append(f"Audio/video sync drift {sync_validation.drift_seconds:.3f}s exceeds 50ms tolerance.")

        # Subtitles check
        if subtitle_validation.issues:
            warnings.extend(subtitle_validation.issues)

        # 2. Scene Composite Quality (60 pts)
        if scene_scores:
            avg_scene = sum(s.composite_scene_score for s in scene_scores) / len(scene_scores)
            scene_pts = avg_scene * 0.60
        else:
            scene_pts = 50.0 * 0.60

        total_score = round(min(max(objective_pts + scene_pts, 0.0), 100.0), 1)
        passed = (total_score >= 70.0) and (len(failures) == 0)

        return total_score, passed, warnings, failures
