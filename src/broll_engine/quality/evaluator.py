"""Automated Video Quality Assessment orchestrator (Phase 6)."""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from broll_engine.logging import get_logger
from broll_engine.models.retrieval import SelectedClip
from broll_engine.models.scenes import Scene
from broll_engine.quality.models import SaliencyCropReport, VideoQualityReport
from broll_engine.quality.saliency import VisualSaliencyAnalyzer
from broll_engine.quality.scorer import QualityScorer
from broll_engine.quality.video_inspector import VideoQualityInspector

logger = get_logger(__name__)


class VideoQualityEvaluator:
    """Orchestrates comprehensive objective and heuristic quality assessment for generated videos."""

    def __init__(
        self,
        inspector: Optional[VideoQualityInspector] = None,
        saliency_analyzer: Optional[VisualSaliencyAnalyzer] = None,
        scorer: Optional[QualityScorer] = None,
    ):
        self.inspector = inspector or VideoQualityInspector()
        self.saliency = saliency_analyzer or VisualSaliencyAnalyzer()
        self.scorer = scorer or QualityScorer()

    async def evaluate_video_quality(
        self,
        video_paths: Dict[str, str],
        scenes: List[Scene],
        clips: List[SelectedClip],
        srt_content: str = "",
        primary_aspect_ratio: str = "16:9",
    ) -> VideoQualityReport:
        """Evaluates rendered videos across objective standards, composition, and scene pacing."""
        primary_video = video_paths.get(primary_aspect_ratio) or next(iter(video_paths.values()), "")

        logger.info("Evaluating quality for primary video: %s", primary_video)

        # 1. Objective Video Inspections (Concurrent)
        black_frames_task = self.inspector.detect_black_frames(primary_video)
        frozen_frames_task = self.inspector.detect_frozen_frames(primary_video)
        streams_task = self.inspector.validate_streams(primary_video, expected_aspect=primary_aspect_ratio)
        sync_task = self.inspector.validate_audio_sync(primary_video)

        black_res, frozen_res, stream_res, sync_res = await asyncio.gather(
            black_frames_task, frozen_frames_task, streams_task, sync_task
        )

        # 2. Subtitle Validation
        sub_res = self.inspector.validate_subtitles(
            srt_content=srt_content,
            video_duration=sync_res.video_duration_seconds,
        )

        # 3. Visual Saliency / Composition Assessment across all aspect ratios
        saliency_reports: Dict[str, SaliencyCropReport] = {}
        for aspect, path in video_paths.items():
            saliency_reports[aspect] = await self.saliency.evaluate_composition(
                video_path=path,
                aspect_ratio=aspect,
            )

        # 4. Scene-Level Quality Scoring
        clip_counts: Dict[str, int] = {}
        for c in clips:
            clip_counts[c.asset_id] = clip_counts.get(c.asset_id, 0) + 1

        clip_map = {c.scene_id: c for c in clips}
        scene_scores = [
            self.scorer.score_scene(scene=sc, clip=clip_map.get(sc.id), used_clip_ids=clip_counts)
            for sc in scenes
        ]

        # 5. Composite Quality Score Calculation
        overall_score, passed, warnings, failures = self.scorer.compute_overall_quality(
            scene_scores=scene_scores,
            stream_validation=stream_res,
            black_frames=black_res,
            frozen_frames=frozen_res,
            sync_validation=sync_res,
            subtitle_validation=sub_res,
        )

        objective_metrics = {
            "stream_validation": stream_res.model_dump(),
            "black_frames": black_res.model_dump(),
            "frozen_frames": frozen_res.model_dump(),
            "audio_sync": sync_res.model_dump(),
            "subtitle_validation": sub_res.model_dump(),
        }

        heuristic_metrics = {
            "saliency_composition": {k: v.model_dump() for k, v in saliency_reports.items()},
            "average_scene_relevance": (
                round(sum(s.relevance_score for s in scene_scores) / len(scene_scores), 2)
                if scene_scores
                else 0.0
            ),
            "average_pacing_score": (
                round(sum(s.pacing_score for s in scene_scores) / len(scene_scores), 1)
                if scene_scores
                else 0.0
            ),
        }

        return VideoQualityReport(
            overall_quality_score=overall_score,
            passed=passed,
            objective_metrics=objective_metrics,
            heuristic_metrics=heuristic_metrics,
            scene_scores=scene_scores,
            saliency_reports=saliency_reports,
            warnings=warnings,
            failures=failures,
        )
