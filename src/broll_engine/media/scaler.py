"""Video scaling, cropping, and aspect ratio adaptation engine (Phase 5)."""

from typing import Dict, Tuple

ASPECT_RATIO_CONFIGS: Dict[str, Dict[str, any]] = {
    "16:9": {
        "width": 1920,
        "height": 1080,
        "label": "Landscape Full HD",
        "sar": "1/1",
        "dar": "16/9",
    },
    "9:16": {
        "width": 1080,
        "height": 1920,
        "label": "Vertical Mobile / Shorts",
        "sar": "1/1",
        "dar": "9/16",
    },
    "1:1": {
        "width": 1080,
        "height": 1080,
        "label": "Square Social Feed",
        "sar": "1/1",
        "dar": "1/1",
    },
}


class VideoScaler:
    """Computes exact geometry and FFmpeg filtergraphs for multi-aspect video scaling."""

    @classmethod
    def get_dimensions(cls, aspect_ratio: str) -> Tuple[int, int]:
        cfg = ASPECT_RATIO_CONFIGS.get(aspect_ratio, ASPECT_RATIO_CONFIGS["16:9"])
        return cfg["width"], cfg["height"]

    @classmethod
    def build_scale_crop_filter(
        cls,
        target_aspect_ratio: str,
        fps: int = 30,
    ) -> str:
        """Constructs an FFmpeg video filtergraph that scales and center-crops

        input footage to the exact target dimensions without distortion or black bars.
        """
        width, height = cls.get_dimensions(target_aspect_ratio)
        return (
            f"scale=w={width}:h={height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"fps={fps},"
            f"settb=AVTB,"
            f"setpts=PTS-STARTPTS,"
            f"format=yuv420p"
        )
