"""Semantic relevance ranking and explanation engine for B-roll footage (Phase 4)."""

import re
from typing import List, Optional, Set, Tuple
from broll_engine.logging import get_logger
from broll_engine.models.retrieval import CandidateAsset, RankedAsset

logger = get_logger(__name__)

STOP_WORDS = {
    "a", "an", "the", "in", "on", "at", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below", "to", "from",
    "up", "down", "in", "out", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don",
    "should", "now", "video", "footage", "clip", "modern", "bright", "real", "world",
}

# Domain conflict rules for homonym protection
HOMONYM_CONFLICTS = {
    "cloud": {
        "tech_indicators": {"computing", "server", "servers", "datacenter", "database", "it", "code", "software", "network", "devops"},
        "sky_indicators": {"sky", "weather", "clouds", "cumulus", "rain", "storm", "sunset", "atmosphere", "horizon", "blue sky"},
    },
    "python": {
        "tech_indicators": {"programming", "code", "developer", "software", "script", "computer", "ide", "syntax", "engineer"},
        "nature_indicators": {"snake", "reptile", "serpent", "wildlife", "jungle", "zoo", "scales", "terrarium"},
    },
    "apple": {
        "tech_indicators": {"iphone", "macbook", "ipad", "laptop", "smartphone", "ios", "gadget", "device"},
        "nature_indicators": {"fruit", "orchard", "harvest", "crisp", "tree", "red apple", "green apple", "eating"},
    },
    "bank": {
        "finance_indicators": {"money", "finance", "banking", "currency", "financial", "investment", "vault", "cash"},
        "river_indicators": {"river", "water", "stream", "lake", "shore", "mud", "grass", "creek"},
    },
}


class SemanticRelevanceRanker:
    """Evaluates and ranks candidate assets against scene visual queries and intent."""

    def __init__(self, min_threshold: float = 0.45):
        self.min_threshold = min_threshold

    def _tokenize(self, text: str) -> Set[str]:
        if not text:
            return set()
        words = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", text.lower())
        return {w for w in words if w not in STOP_WORDS}

    def _check_homonym_penalty(
        self,
        scene_tokens: Set[str],
        candidate_tokens: Set[str],
        visual_intent: str,
    ) -> Tuple[float, Optional[str]]:
        """Applies severe penalty if a candidate matches a literal homonym contrary to scene intent."""
        for term, data in HOMONYM_CONFLICTS.items():
            if term in scene_tokens or (visual_intent == "technology" and term == "cloud"):
                # Scene is about technology (e.g. cloud computing)
                if (data["tech_indicators"] & scene_tokens) or visual_intent == "technology":
                    # If candidate has sky indicators and no tech indicators, disqualify
                    if (data["sky_indicators"] if "sky_indicators" in data else data.get("nature_indicators", set())) & candidate_tokens:
                        if not (data["tech_indicators"] & candidate_tokens):
                            return 0.85, f"Homonym collision: scene intended '{term} (tech)' but candidate depicted atmospheric/nature '{term}'."

                # Scene is about nature/sky
                sky_or_nature = data.get("sky_indicators", data.get("nature_indicators", set()))
                if (sky_or_nature & scene_tokens) or visual_intent in ("nature", "environment"):
                    if data["tech_indicators"] & candidate_tokens:
                        if not (sky_or_nature & candidate_tokens):
                            return 0.85, f"Homonym collision: scene intended natural '{term}' but candidate depicted tech '{term}'."

        return 0.0, None

    def rank_candidate(
        self,
        candidate: CandidateAsset,
        visual_query: str,
        narration_text: str = "",
        visual_intent: str = "generic",
        negative_constraints: Optional[List[str]] = None,
        requested_aspect: str = "16:9",
    ) -> RankedAsset:
        """Scores a single candidate asset."""
        query_tokens = self._tokenize(visual_query)
        narration_tokens = self._tokenize(narration_text)
        all_scene_tokens = query_tokens | narration_tokens

        candidate_tag_tokens = set()
        for t in candidate.tags:
            candidate_tag_tokens.update(self._tokenize(t))
        candidate_title_tokens = self._tokenize(candidate.title)
        candidate_desc_tokens = self._tokenize(candidate.description or "")
        all_candidate_tokens = candidate_tag_tokens | candidate_title_tokens | candidate_desc_tokens

        matched = sorted(list(query_tokens & all_candidate_tokens))

        # 1. Lexical overlap ratio
        if query_tokens:
            overlap_ratio = len(matched) / min(max(len(query_tokens), 1), 6)
            overlap_score = min(overlap_ratio, 1.0) * 0.70
        else:
            overlap_score = 0.30

        # 2. Intent alignment bonus
        intent_bonus = 0.0
        if visual_intent and visual_intent != "generic":
            intent_tokens = self._tokenize(visual_intent)
            if intent_tokens & all_candidate_tokens or visual_intent in candidate.tags:
                intent_bonus = 0.15

        # 3. Aspect ratio alignment bonus
        aspect_bonus = 0.10 if candidate.aspect_ratio == requested_aspect else 0.0

        # 4. Homonym conflict check
        homonym_penalty, homonym_reason = self._check_homonym_penalty(
            scene_tokens=all_scene_tokens,
            candidate_tokens=all_candidate_tokens,
            visual_intent=visual_intent,
        )

        # 5. Negative constraint penalty
        neg_penalty = 0.0
        neg_matches = []
        if negative_constraints:
            for neg in negative_constraints:
                neg_tokens = self._tokenize(neg)
                if neg_tokens and (neg_tokens & all_candidate_tokens):
                    neg_penalty += 0.40
                    neg_matches.append(neg)

        total_penalty = homonym_penalty + neg_penalty

        # Compute raw normalized ratio [0.0, 1.0]
        raw_ratio = max(0.0, min(1.0, overlap_score + intent_bonus + aspect_bonus - total_penalty))

        # Procedural fallback gets guaranteed baseline score (0.60 / 3.0) if it is procedural
        if candidate.is_procedural:
            raw_ratio = 0.70
            matched = ["procedural_motion", visual_intent]

        relevance_ratio = round(raw_ratio, 3)
        relevance_score = round(relevance_ratio * 5.0, 2)

        # Build human-readable explanation
        reasons = []
        if matched:
            reasons.append(f"Matched keywords: {matched[:5]}")
        if intent_bonus > 0:
            reasons.append(f"aligned with intent '{visual_intent}' (+0.15)")
        if aspect_bonus > 0:
            reasons.append(f"native aspect ratio '{requested_aspect}' (+0.10)")
        if homonym_reason:
            reasons.append(f"PENALTY: {homonym_reason}")
        if neg_matches:
            reasons.append(f"PENALTY: Matched negative constraints: {neg_matches}")

        selection_reason = "; ".join(reasons) if reasons else "Generic baseline relevance"

        return RankedAsset(
            candidate=candidate,
            relevance_score=relevance_score,
            relevance_ratio=relevance_ratio,
            selection_reason=selection_reason,
            matched_keywords=matched,
            penalty_applied=round(total_penalty, 2),
        )

    def rank_candidates(
        self,
        candidates: List[CandidateAsset],
        visual_query: str,
        narration_text: str = "",
        visual_intent: str = "generic",
        negative_constraints: Optional[List[str]] = None,
        requested_aspect: str = "16:9",
    ) -> List[RankedAsset]:
        """Ranks a list of candidate assets, sorted descending by relevance score."""
        ranked = [
            self.rank_candidate(
                candidate=c,
                visual_query=visual_query,
                narration_text=narration_text,
                visual_intent=visual_intent,
                negative_constraints=negative_constraints,
                requested_aspect=requested_aspect,
            )
            for c in candidates
        ]
        # Sort descending by relevance ratio
        ranked.sort(key=lambda r: r.relevance_ratio, reverse=True)
        return ranked
