"""Deterministic procedural graphics fallback generator using FFmpeg (Phase 4)."""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import List, Optional
from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.models.retrieval import (
    AssetLicense,
    CandidateAsset,
    VideoFile,
)
from broll_engine.retrieval.base import BaseFootageProvider

logger = get_logger(__name__)

THEME_PALETTES = {
    "technology": {
        "c0": "0x0a192f",  # Deep tech indigo
        "c1": "0x00b4d8",  # Cyber cyan
        "speed": "0.015",
    },
    "business": {
        "c0": "0x1a202c",  # Modern charcoal
        "c1": "0xd69e2e",  # Executive gold
        "speed": "0.01",
    },
    "finance": {
        "c0": "0x0d1f2d",  # Banking navy
        "c1": "0x546a7b",  # Steel slate
        "speed": "0.01",
    },
    "nature": {
        "c0": "0x064e3b",  # Deep forest emerald
        "c1": "0x10b981",  # Fresh growth green
        "speed": "0.012",
    },
    "growth": {
        "c0": "0x064e3b",
        "c1": "0x34d399",
        "speed": "0.015",
    },
    "security": {
        "c0": "0x0f172a",  # Cyber slate
        "c1": "0x2563eb",  # Secure cobalt
        "speed": "0.01",
    },
    "creative": {
        "c0": "0x2e1065",  # Deep violet
        "c1": "0xc026d3",  # Dynamic fuchsia
        "speed": "0.02",
    },
    "default": {
        "c0": "0x111827",  # Minimalist dark
        "c1": "0x3b82f6",  # Electric blue
        "speed": "0.012",
    },
}

ASPECT_DIMENSIONS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}


class ProceduralFallbackProvider(BaseFootageProvider):
    """Generates high-definition, commercially cleared procedural motion clips."""

    LICENSE_URL = "https://incubrix.internal/licenses/procedural-cc0"

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir or settings.footage_cache_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def provider_name(self) -> str:
        return "procedural"

    @property
    def is_configured(self) -> bool:
        return True  # Zero external API dependencies

    def _resolve_palette(self, theme: str) -> dict:
        theme_clean = theme.lower().strip()
        for key, palette in THEME_PALETTES.items():
            if key in theme_clean:
                return palette
        return THEME_PALETTES["default"]

    async def search_videos(
        self,
        query: str,
        aspect_ratio: str = "16:9",
        per_page: int = 2,
    ) -> List[CandidateAsset]:
        """Synthesizes candidate procedural asset definitions for query."""
        width, height = ASPECT_DIMENSIONS.get(aspect_ratio, (1920, 1080))
        palette = self._resolve_palette(query)
        asset_id = f"procedural_{abs(hash(query)) % 1000000:06d}_{aspect_ratio.replace(':', 'x')}"

        license_meta = AssetLicense(
            license_name="Procedurally Generated (Commercial CC0 Equivalent)",
            license_url=self.LICENSE_URL,
            commercial_use_eligible=True,
            attribution_required=False,
            attribution_text="Procedural visual synthesized by IncuBrix B-roll Engine",
            clearance_status="commercial_cleared",
            verification_notes="100% synthetically generated offline via FFmpeg shader pipeline.",
        )

        dummy_path = str(self.output_dir / f"{asset_id}.mp4")

        candidate = CandidateAsset(
            asset_id=asset_id,
            provider=self.provider_name,
            title=f"Procedural Motion: {query[:30]}",
            description="High-definition procedural geometric gradient background",
            tags=["procedural", "motion", "gradient", "background", query[:20]],
            duration_seconds=10.0,
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            creator_name="IncuBrix Procedural Engine",
            creator_url="https://incubrix.internal",
            original_page_url="https://incubrix.internal/procedural",
            download_url=f"file://{dummy_path}",
            license=license_meta,
            is_ai_generated=False,
            is_procedural=True,
            video_files=[
                VideoFile(
                    id=f"{asset_id}_hd",
                    quality="hd",
                    width=width,
                    height=height,
                    fps=30.0,
                    link=f"file://{dummy_path}",
                    file_type="video/mp4",
                )
            ],
        )
        return [candidate]

    async def generate_clip(
        self,
        target_path: str,
        duration: float,
        aspect_ratio: str = "16:9",
        theme: str = "default",
    ) -> str:
        """Renders the actual MP4 file via FFmpeg lavfi filtergraph asynchronously."""
        target_file = Path(target_path)
        target_file.parent.mkdir(parents=True, exist_ok=True)

        width, height = ASPECT_DIMENSIONS.get(aspect_ratio, (1920, 1080))
        palette = self._resolve_palette(theme)
        dur = max(duration, 1.0)

        # lavfi gradients filter creates smooth dynamic color transitions
        lavfi_filter = (
            f"gradients=s={width}x{height}:"
            f"c0={palette['c0']}:c1={palette['c1']}:"
            f"speed={palette['speed']}:d={dur:.2f}:r=30"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", lavfi_filter,
            "-t", f"{dur:.2f}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            "-crf", "22",
            str(target_file),
        ]

        logger.info(
            "Synthesizing procedural clip %s (%dx%d, %.2fs, theme=%s)",
            target_file.name,
            width,
            height,
            dur,
            theme,
        )

        loop = asyncio.get_running_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            ),
        )

        if proc.returncode != 0:
            err_msg = proc.stderr.decode(errors="replace")
            logger.error("FFmpeg procedural rendering failed: %s", err_msg)
            # Fallback to solid color if gradients filter is unsupported on host
            fallback_cmd = [
                "ffmpeg",
                "-y",
                "-f", "lavfi",
                "-i", f"color=c=0x0a192f:s={width}x{height}:r=30",
                "-t", f"{dur:.2f}",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "ultrafast",
                str(target_file),
            ]
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True),
            )

        return str(target_file)
