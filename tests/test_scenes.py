import pytest
from httpx import AsyncClient

from broll_engine.api.schemas.job import SceneHint
from broll_engine.models.scenes import (
    PacingStatus,
    SceneSegmentationResult,
    SegmentationReason,
    TimingSource,
)
from broll_engine.scenes.disambiguation import ContextualQueryDisambiguator
from broll_engine.scenes.pacing import PacingGuard
from broll_engine.scenes.segmenter import SemanticSceneSegmenter
from broll_engine.speech.asr.base import WordTiming


def create_mock_word_timings(words: list, total_duration: float) -> list:
    """Evenly distributes words across total_duration."""
    n = len(words)
    w_dur = total_duration / float(n)
    timings = []
    for i, w in enumerate(words):
        timings.append(
            WordTiming(
                word=w,
                start=round(i * w_dur, 3),
                end=round((i + 1) * w_dur, 3),
                probability=0.99,
            )
        )
    return timings


def test_pacing_guard_splits_long_scene():
    """Verifies that scenes exceeding 5.0s are split into valid sub-scenes."""
    guard = PacingGuard(min_duration_seconds=1.8, max_duration_seconds=5.0)

    # 8.0s scene with 16 words
    text = "Artificial intelligence enables rapid video production and transforms digital creator workflows across global markets."
    words_list = text.split()
    word_timings = create_mock_word_timings(words_list, total_duration=8.0)

    from broll_engine.models.scenes import Scene
    long_scene = Scene(
        id="scene_001",
        index=0,
        start_seconds=0.0,
        end_seconds=8.0,
        duration_seconds=8.0,
        narration_text=text,
        language="en",
        visual_query="technology",
        words=word_timings,
    )

    paced = guard.enforce_pacing([long_scene], total_audio_duration=8.0)

    assert len(paced) >= 2
    for sc in paced:
        assert 1.8 <= sc.duration_seconds <= 5.0
        assert sc.pacing_status == PacingStatus.SPLIT_OVER_MAX


def test_pacing_guard_merges_short_final_scene():
    """Verifies that short trailing scenes (<1.8s) are merged backward without losing narration."""
    guard = PacingGuard(min_duration_seconds=1.8, max_duration_seconds=5.0)

    from broll_engine.models.scenes import Scene
    sc1 = Scene(
        id="scene_001",
        index=0,
        start_seconds=0.0,
        end_seconds=3.0,
        duration_seconds=3.0,
        narration_text="Welcome to the video engine.",
        language="en",
        visual_query="technology",
        words=create_mock_word_timings("Welcome to the video engine.".split(), 3.0),
    )
    sc2 = Scene(
        id="scene_002",
        index=1,
        start_seconds=3.0,
        end_seconds=4.0,  # 1.0s: under 1.8s limit
        duration_seconds=1.0,
        narration_text="Start now.",
        language="en",
        visual_query="action",
        words=create_mock_word_timings("Start now.".split(), 1.0),
    )

    paced = guard.enforce_pacing([sc1, sc2], total_audio_duration=4.0)

    assert len(paced) == 1
    assert paced[0].duration_seconds == 4.0
    assert "Start now." in paced[0].narration_text
    assert paced[0].pacing_status == PacingStatus.MERGED_UNDER_MIN


def test_timeline_continuous_coverage_zero_gaps_zero_overlaps():
    """Verifies zero gaps and zero overlaps across a segmented timeline."""
    segmenter = SemanticSceneSegmenter()
    text = (
        "IncuBrix is an automated video engine. "
        "It generates broadcast ready B-roll clips. "
        "Every second of audio is covered without any black frames or visual drift."
    )
    words = create_mock_word_timings(text.split(), total_duration=9.5)

    res: SceneSegmentationResult = segmenter.segment(
        transcript_text=text,
        words=words,
        total_duration_seconds=9.5,
        language="en",
        timing_source=TimingSource.ASR_ACOUSTIC,
    )

    assert res.has_gaps is False
    assert res.has_overlaps is False
    assert res.scenes[0].start_seconds == 0.0
    assert res.scenes[-1].end_seconds == 9.5

    # Verify every adjacent scene matches exactly
    for i in range(1, len(res.scenes)):
        prev = res.scenes[i - 1]
        curr = res.scenes[i]
        assert abs(curr.start_seconds - prev.end_seconds) < 0.001


def test_homonym_disambiguation_cloud():
    """Verifies contextual disambiguation for 'cloud' (datacenter vs weather)."""
    disambiguator = ContextualQueryDisambiguator()

    # Cloud in computing context
    query_tech, intent_tech, _ = disambiguator.disambiguate_scene(
        scene_text="Deploying server instances on the cloud infrastructure.",
        full_context="Our software engineering team uses cloud computing data storage and kubernetes clusters.",
    )
    assert "datacenter" in query_tech or "server" in query_tech
    assert intent_tech == "technology"

    # Cloud in nature context
    query_sky, intent_sky, _ = disambiguator.disambiguate_scene(
        scene_text="White clouds drifted gently across the horizon.",
        full_context="The weather was clear with a bright blue sky, sunlight and gentle wind.",
    )
    assert "sky" in query_sky or "clouds" in query_sky
    assert intent_sky == "environment"


def test_homonym_disambiguation_python():
    """Verifies contextual disambiguation for 'python' (programming vs reptile)."""
    disambiguator = ContextualQueryDisambiguator()

    # Python programming
    query_code, intent_code, _ = disambiguator.disambiguate_scene(
        scene_text="Write a python script to automate the pipeline.",
        full_context="The developer opens the terminal to execute the python backend code.",
    )
    assert "developer" in query_code or "code" in query_code
    assert intent_code == "technology"

    # Python snake
    query_snake, intent_snake, _ = disambiguator.disambiguate_scene(
        scene_text="A large python rested in the branches.",
        full_context="Exploring the tropical wildlife jungle with rare reptiles, snakes, and exotic animals.",
    )
    assert "snake" in query_snake or "wildlife" in query_snake
    assert intent_snake == "environment"


def test_abstract_concept_metaphors():
    """Verifies mapping abstract concepts into concrete visual metaphors."""
    disambiguator = ContextualQueryDisambiguator()

    # Trust / Integrity
    q_trust, intent_trust, _ = disambiguator.disambiguate_scene(
        scene_text="Building enduring trust with clients.",
        full_context="Integrity and long term trust are the cornerstone of our corporate partnership.",
    )
    assert "handshake" in q_trust or "conference room" in q_trust
    assert intent_trust == "metaphor"

    # Innovation
    q_innov, intent_innov, _ = disambiguator.disambiguate_scene(
        scene_text="Pioneering breakthrough innovation.",
        full_context="Our research laboratory is dedicated to technological innovation.",
    )
    assert "laboratory" in q_innov or "technology" in q_innov
    assert intent_innov == "technology"

    # Growth
    q_growth, intent_growth, _ = disambiguator.disambiguate_scene(
        scene_text="Achieving exponential business growth.",
        full_context="Revenue growth and expansion across new markets.",
    )
    assert "sprout" in q_growth or "chart" in q_growth
    assert intent_growth == "metaphor"


def test_multilingual_segmentation_hindi():
    """Verifies Hindi scene segmentation and visual concept mapping."""
    segmenter = SemanticSceneSegmenter()
    hindi_text = "तकनीक और नवाचार हमारे काम करने के तरीके को बदल रहे हैं। हम नए विकास की ओर बढ़ रहे हैं।"
    words = create_mock_word_timings(hindi_text.split(), total_duration=6.5)

    res: SceneSegmentationResult = segmenter.segment(
        transcript_text=hindi_text,
        words=words,
        total_duration_seconds=6.5,
        language="hi",
        timing_source=TimingSource.TTS_INTERPOLATED,
    )

    assert res.scene_count >= 1
    assert res.timing_source == TimingSource.TTS_INTERPOLATED
    assert res.has_gaps is False
    assert res.has_overlaps is False
    # Verify visual query is grounded
    assert len(res.scenes[0].visual_query) > 0


def test_multilingual_segmentation_tamil():
    """Verifies Tamil scene segmentation and visual concept mapping."""
    segmenter = SemanticSceneSegmenter()
    tamil_text = "தொழில்நுட்பம் மனித வாழ்க்கையை எளிதாக்குகிறது. புதிய வளர்ச்சி தொடங்குகிறது."
    words = create_mock_word_timings(tamil_text.split(), total_duration=5.5)

    res: SceneSegmentationResult = segmenter.segment(
        transcript_text=tamil_text,
        words=words,
        total_duration_seconds=5.5,
        language="ta",
        timing_source=TimingSource.ASR_ACOUSTIC,
    )

    assert res.scene_count >= 1
    assert res.timing_source == TimingSource.ASR_ACOUSTIC
    assert res.has_gaps is False
    assert res.has_overlaps is False
    assert len(res.scenes[0].visual_query) > 0


def test_safety_constraints_and_user_avoid():
    """Verifies negative constraints include standard face/logo guardrails and user avoid list."""
    disambiguator = ContextualQueryDisambiguator()
    _, _, negatives = disambiguator.disambiguate_scene(
        scene_text="High speed innovation.",
        full_context="Technology and speed.",
        user_avoid_list=["cartoons", "crowded stadiums"],
    )

    assert "identifiable real people faces" in negatives
    assert "celebrity faces" in negatives
    assert "copyrighted brand logos" in negatives
    assert "watermarks" in negatives
    assert "cartoons" in negatives
    assert "crowded stadiums" in negatives


def test_director_scene_hints_handling():
    """Verifies that director scene hints guide segmentation boundaries and queries."""
    segmenter = SemanticSceneSegmenter()
    hints = [
        SceneHint(text="First scene introduction.", visual_hint="aerial view of sunrise over ocean"),
        SceneHint(text="Second scene demonstration.", visual_hint="close up hands typing on laptop"),
    ]
    all_words = create_mock_word_timings("First scene introduction. Second scene demonstration.".split(), 6.0)

    res = segmenter.segment(
        transcript_text="First scene introduction. Second scene demonstration.",
        words=all_words,
        total_duration_seconds=6.0,
        scenes_hint=hints,
    )

    assert res.scene_count == 2
    assert res.scenes[0].segmentation_reason == SegmentationReason.DIRECTOR_HINT
    assert "aerial view of sunrise" in res.scenes[0].visual_query
    assert "close up hands typing" in res.scenes[1].visual_query


@pytest.mark.asyncio
async def test_end_to_end_job_produces_scenes_json_and_rich_timeline(client: AsyncClient):
    """Verifies that submitting a job generates scenes.json and a fully segmented timeline."""
    payload = {
        "script": "Artificial intelligence creates video content. It analyzes speech and retrieves matching visual scenes.",
        "voice": "en-IN-female",
        "aspect_ratios": ["16:9"],
        "avoid": ["brand logos", "cluttered backgrounds"],
    }

    res = await client.post("/api/v1/broll/jobs", json=payload)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    import asyncio
    for _ in range(30):
        detail = (await client.get(f"/api/v1/jobs/{job_id}")).json()
        if detail["status"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.05)

    assert detail["status"] == "succeeded"
    outputs = detail["outputs"]

    assert "scenes" in outputs
    assert outputs["scenes"] is not None
    assert "timeline" in outputs
    assert outputs["timeline"] is not None
