"""Deduplication and near-duplicate prevention engine (Phase 4)."""

import hashlib
import re
from typing import Dict, List, Optional, Set, Tuple
from broll_engine.logging import get_logger
from broll_engine.models.retrieval import CandidateAsset, DeduplicationReport, RankedAsset

logger = get_logger(__name__)


class ClipDeduplicator:
    """Tracks and prevents duplicate or near-duplicate clip selections across scenes."""

    def __init__(self, near_duplicate_threshold: float = 0.80):
        self.near_duplicate_threshold = near_duplicate_threshold
        self.used_asset_ids: Set[str] = set()
        self.used_content_hashes: Set[str] = set()
        self.used_urls: Set[str] = set()
        self.selected_candidates: List[CandidateAsset] = []

        # Audit counters
        self.duplicate_rejected_count: int = 0
        self.near_duplicate_rejected_count: int = 0
        self.procedural_fallback_count: int = 0

    def is_exact_duplicate(self, candidate: CandidateAsset) -> bool:
        """Checks if asset ID or download URL was already used in this video."""
        if candidate.asset_id in self.used_asset_ids:
            return True
        if candidate.download_url in self.used_urls:
            return True
        return False

    def is_near_duplicate(self, candidate: CandidateAsset) -> Tuple[bool, Optional[str]]:
        """Detects whether candidate is practically identical to an already selected clip."""
        cand_tokens = set(re.findall(r"\b\w{3,}\b", (candidate.title + " " + " ".join(candidate.tags)).lower()))
        if not cand_tokens:
            return False, None

        for prev in self.selected_candidates:
            # If from different authors, less likely to be identical sequence
            if prev.creator_name and candidate.creator_name and prev.creator_name == candidate.creator_name:
                prev_tokens = set(re.findall(r"\b\w{3,}\b", (prev.title + " " + " ".join(prev.tags)).lower()))
                if not prev_tokens:
                    continue
                intersection = len(cand_tokens & prev_tokens)
                union = len(cand_tokens | prev_tokens)
                jaccard = intersection / max(union, 1)
                overlap_ratio = intersection / min(len(cand_tokens), len(prev_tokens))

                if jaccard >= self.near_duplicate_threshold or overlap_ratio >= 0.60:
                    return True, (
                        f"Near-duplicate of clip '{prev.asset_id}' by same creator '{candidate.creator_name}' "
                        f"(token overlap: {overlap_ratio:.2f}, jaccard: {jaccard:.2f})"
                    )

        return False, None

    def filter_and_select_best(
        self,
        ranked_candidates: List[RankedAsset],
        min_threshold: float = 0.45,
    ) -> Optional[RankedAsset]:
        """Selects the highest-ranked candidate that is neither duplicate nor near-duplicate.

        Args:
            ranked_candidates: Candidates sorted descending by relevance score.
            min_threshold: Minimum acceptable relevance ratio (0.0 to 1.0).

        Returns:
            The best unique RankedAsset, or None if all candidates are duplicate/below threshold.
        """
        for ranked in ranked_candidates:
            candidate = ranked.candidate

            # Check exact duplicates
            if self.is_exact_duplicate(candidate):
                logger.info(
                    "Deduplication: Rejected exact duplicate asset '%s' (relevance: %.2f)",
                    candidate.asset_id,
                    ranked.relevance_score,
                )
                self.duplicate_rejected_count += 1
                continue

            # Check near-duplicates
            is_near, reason = self.is_near_duplicate(candidate)
            if is_near:
                logger.info(
                    "Deduplication: Rejected near-duplicate asset '%s': %s",
                    candidate.asset_id,
                    reason,
                )
                self.near_duplicate_rejected_count += 1
                continue

            # Check minimum relevance score threshold
            if ranked.relevance_ratio < min_threshold and not candidate.is_procedural:
                logger.info(
                    "Deduplication: Candidate '%s' score %.2f is below threshold %.2f",
                    candidate.asset_id,
                    ranked.relevance_ratio,
                    min_threshold,
                )
                continue

            # Passed all deduplication and relevance checks
            self.register_selection(candidate)
            return ranked

        return None

    def register_selection(self, candidate: CandidateAsset, content_hash: Optional[str] = None):
        """Records an accepted asset into the deduplication registry."""
        self.used_asset_ids.add(candidate.asset_id)
        self.used_urls.add(candidate.download_url)
        self.selected_candidates.append(candidate)
        if content_hash:
            self.used_content_hashes.add(content_hash)
        if candidate.is_procedural:
            self.procedural_fallback_count += 1

    def generate_report(self) -> DeduplicationReport:
        """Returns the final deduplication audit metrics."""
        return DeduplicationReport(
            unique_clips_selected=len(self.used_asset_ids),
            duplicate_candidates_rejected=self.duplicate_rejected_count,
            near_duplicates_rejected=self.near_duplicate_rejected_count,
            procedural_fallbacks_invoked=self.procedural_fallback_count,
            used_asset_ids=sorted(list(self.used_asset_ids)),
        )
