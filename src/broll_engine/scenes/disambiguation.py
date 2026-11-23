import re
from typing import Dict, List, Optional, Set, Tuple


# Standard safety constraints enforced on all B-roll queries to guarantee commercial compliance
DEFAULT_NEGATIVE_CONSTRAINTS = [
    "identifiable real people faces",
    "celebrity faces",
    "politicians",
    "copyrighted brand logos",
    "watermarks",
    "stock footage overlay text",
    "low resolution",
    "blurry frames",
    "violence",
]

# Homonym disambiguation dictionary: term -> [(set_of_context_keywords, visual_query, visual_intent)]
HOMONYM_DISAMBIGUATION_MAP: Dict[str, List[Tuple[Set[str], str, str]]] = {
    "cloud": [
        (
            {"computing", "server", "servers", "data", "software", "aws", "azure", "storage",
             "infrastructure", "devops", "deploy", "api", "cluster", "digital", "network", "tech", "engine"},
            "datacenter server racks glowing blue lights technology",
            "technology",
        ),
        (
            {"sky", "weather", "rain", "storm", "sun", "blue", "wind", "airplane", "horizon", "nature", "outdoor"},
            "dramatic blue sky white puffy clouds time lapse",
            "environment",
        ),
    ],
    "python": [
        (
            {"code", "programming", "script", "developer", "software", "language", "data", "engineer",
             "backend", "django", "fastapi", "machine", "algorithm", "computer"},
            "software developer typing python code on screen modern office",
            "technology",
        ),
        (
            {"snake", "reptile", "jungle", "zoo", "wildlife", "animal", "forest", "tree", "species"},
            "python snake in lush green tropical foliage wildlife",
            "environment",
        ),
    ],
    "apple": [
        (
            {"iphone", "macbook", "ipad", "ios", "computer", "device", "silicon", "store", "tech", "laptop"},
            "sleek modern smartphone and laptop on clean minimalist desk",
            "technology",
        ),
        (
            {"fruit", "orchard", "tree", "eat", "pie", "red", "green", "healthy", "food", "harvest"},
            "fresh crisp red apples hanging on tree in orchard sunlight",
            "environment",
        ),
    ],
    "bank": [
        (
            {"money", "finance", "loan", "investment", "account", "interest", "economy", "capital", "cash"},
            "modern financial district glass skyscrapers banking commerce",
            "concrete_action",
        ),
        (
            {"river", "water", "stream", "shore", "mud", "grass", "fishing", "lake", "nature"},
            "green grassy river bank flowing clear clean water nature",
            "environment",
        ),
    ],
    "current": [
        (
            {"electric", "electrical", "voltage", "wire", "circuit", "amperage", "power", "grid", "energy"},
            "electrical energy glowing blue circuit flow technology",
            "technology",
        ),
        (
            {"water", "ocean", "river", "sea", "stream", "tide", "swim", "waves", "flow"},
            "powerful ocean water current clear turquoise waves moving",
            "environment",
        ),
    ],
    "bug": [
        (
            {"software", "code", "debug", "error", "issue", "patch", "crash", "compiler", "fix", "testing"},
            "software engineer inspecting code debugging on dual monitors",
            "technology",
        ),
        (
            {"insect", "leaf", "garden", "crawl", "plant", "nature", "beetle", "ant"},
            "macro close up colorful insect crawling on green leaf nature",
            "environment",
        ),
    ],
    "pipeline": [
        (
            {"data", "software", "deploy", "build", "process", "workflow", "ci", "cd", "engineering", "automation"},
            "digital data pipeline glowing visual information flow abstract",
            "technology",
        ),
        (
            {"oil", "gas", "water", "steel", "pipe", "construction", "industrial", "refinery"},
            "industrial steel pipeline running through landscape infrastructure",
            "concrete_action",
        ),
    ],
    "scale": [
        (
            {"business", "growth", "users", "system", "infrastructure", "architecture", "scaling", "enterprise"},
            "scalable cloud infrastructure network nodes expanding visually",
            "technology",
        ),
        (
            {"weight", "weigh", "balance", "fish", "measure", "justice", "law", "court"},
            "vintage brass balance scale justice precision close up",
            "metaphor",
        ),
    ],
}

# Abstract concepts mapped to concrete visual metaphors
ABSTRACT_CONCEPT_MAP: List[Tuple[Set[str], str, str]] = [
    (
        {"trust", "integrity", "reliability", "honesty", "credibility"},
        "business partners firm handshake in bright modern conference room agreement",
        "metaphor",
    ),
    (
        {"growth", "increase", "scaling", "expand", "expansion", "profit", "revenue"},
        "timelapse green plant sprout growing through soil or upward financial chart",
        "metaphor",
    ),
    (
        {"innovation", "innovative", "cutting-edge", "breakthrough", "invent", "invention"},
        "modern laboratory scientist engineer working on futuristic technology prototype",
        "technology",
    ),
    (
        {"speed", "fast", "swift", "rapid", "velocity", "accelerate"},
        "high speed train motion blur rushing through futuristic transit terminal",
        "concrete_action",
    ),
    (
        {"security", "privacy", "protection", "safe", "secure", "cybersecurity", "encryption"},
        "digital cyber security padlock shield glowing data protection animation",
        "technology",
    ),
    (
        {"collaboration", "teamwork", "partner", "partnership", "cooperation", "together"},
        "diverse creative team collaborating around whiteboard in modern office",
        "concrete_action",
    ),
    (
        {"future", "vision", "tomorrow", "next-generation"},
        "sleek futuristic city skyline at dawn with autonomous transportation",
        "metaphor",
    ),
    (
        {"global", "world", "worldwide", "international", "globe"},
        "illuminated digital globe rotating with interconnected network lines",
        "technology",
    ),
]

# Multilingual keywords (Hindi and Tamil) to visual queries
MULTILINGUAL_CONCEPT_MAP: List[Tuple[Set[str], str, str]] = [
    # Hindi mappings
    (
        {"तकनीक", "प्रौद्योगिकी", "कंप्यूटर", "सॉफ्टवेयर"},
        "modern computer technology digital innovation workspace",
        "technology",
    ),
    (
        {"नवाचार", "आविष्कार", "रचनात्मक"},
        "creative innovation ideas brainstorming modern tech lab",
        "technology",
    ),
    (
        {"विकास", "प्रगति", "वृद्धि"},
        "modern infrastructure development city skyline economic growth",
        "metaphor",
    ),
    (
        {"विश्वास", "ईमानदारी", "भरोसा"},
        "professional business handshake in conference room agreement",
        "metaphor",
    ),
    (
        {"सुरक्षा", "संरक्षण"},
        "digital data security shield cyber technology",
        "technology",
    ),
    # Tamil mappings
    (
        {"தொழில்நுட்பம்", "கணினி", "மென்பொருள்"},
        "advanced modern technology digital innovation laboratory",
        "technology",
    ),
    (
        {"வளர்ச்சி", "முன்னேற்றம்"},
        "green plant sprout growing sunlight economic growth metaphor",
        "metaphor",
    ),
    (
        {"நம்பிக்கை", "நேர்மை"},
        "business collaboration handshake professional agreement",
        "metaphor",
    ),
    (
        {"பாதுகாப்பு"},
        "digital cybersecurity shield network data protection",
        "technology",
    ),
    (
        {"வெற்றி"},
        "motivated creative professional achieving success modern office",
        "concrete_action",
    ),
]

# Sensitive-topic lexicon: tragic/violent/distressing news handled with respectful,
# non-graphic visual metaphors instead of literal footage searches.
SENSITIVE_TOPIC_KEYWORDS: Set[str] = {
    "war", "wars", "killed", "killing", "murder", "murdered", "death", "deaths", "dead",
    "shooting", "shot", "attack", "attacks", "terrorist", "terrorism", "bombing", "bomb",
    "explosion", "massacre", "genocide", "suicide", "victims", "casualties", "tragedy",
    "disaster", "earthquake", "flood", "famine", "crash", "accident", "abuse",
    "assault", "rape", "kidnapping", "hostage", "execution", "torture", "protest",
    "riot", "riots", "pandemic", "epidemic", "outbreak", "disease",
}

SENSITIVE_TOPIC_QUERY = "somber memorial candles and flowers respectful remembrance vigil"
SENSITIVE_TOPIC_EXTRA_NEGATIVES = [
    "graphic violence",
    "gore",
    "blood",
    "explicit distress",
    "real victims",
]

# Recognized commercial brands. When narration names a brand, the query is rewritten
# to a generic category visual so no trademarked logos or lookalikes are fetched.
KNOWN_BRAND_MAP: Dict[str, str] = {
    "tesla": "electric car", "nike": "athletic running shoes", "adidas": "athletic shoes",
    "coca-cola": "soft drink", "pepsi": "soft drink", "mcdonalds": "fast food restaurant",
    "starbucks": "coffee shop", "google": "search engine office", "microsoft": "corporate software office",
    "amazon": "e-commerce warehouse", "facebook": "social media office", "meta": "social media office",
    "netflix": "streaming entertainment", "spotify": "music streaming", "uber": "ride hailing car",
    "airbnb": "vacation rental apartment", "samsung": "consumer electronics", "sony": "consumer electronics",
    "twitter": "social media feed", "x": "social media feed", "instagram": "social media feed",
    "tiktok": "short video app", "youtube": "online video platform", "openai": "ai research lab",
    "chatgpt": "ai chatbot interface", "iphone": "smartphone", "android": "smartphone",
    "walmart": "retail supermarket", "ikea": "furniture store", "disney": "entertainment company",
    "toyota": "automobile", "bmw": "automobile", "mercedes": "automobile", "ford": "automobile",
    "bitcoin": "cryptocurrency concept", "ethereum": "cryptocurrency concept",
}

BRAND_EXTRA_NEGATIVES = [
    "brand logos",
    "trademarked logos",
    "identifiable brand names",
]

# Capitalized-token heuristic for real named people (e.g. "Elon Musk announced...").
# Two or more consecutive capitalized words not at sentence start are treated as a
# named-person reference and replaced with a generic professional visual.
_NAMED_PERSON_PATTERN = re.compile(r"(?<=[a-z,.;:!?()\-\s])([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)")

# Common non-person capitalized entities that should not trigger the person guard.
_NON_PERSON_ENTITIES: Set[str] = {
    "silicon valley", "new york", "los angeles", "san francisco", "wall street",
    "united states", "united kingdom", "european union", "middle east",
    "south africa", "north america", "south america", "hong kong", "new delhi",
    "latin america", "south korea", "north korea", "great britain",
}

NAMED_PERSON_QUERY = "professional business leader speaking at modern conference podium"
NAMED_PERSON_EXTRA_NEGATIVES = [
    "identifiable real person face",
    "celebrity likeness",
    "politician likeness",
]

# Numbers/statistics → abstract data-visualization metaphors
_STATISTICS_PATTERN = re.compile(
    r"(\d[\d,.]*\s?%|percent|million|billion|trillion|thousand|\$\s?\d|"
    r"\d+\s*(x|times)\b|statistics|statistic|figures?|metrics?|data|survey|study|"
    r"report(ed)?\s+(that|a)\b|increase[sd]?\s+by|decrease[sd]?\s+by|grew\s+by)",
    re.IGNORECASE,
)

STATISTICS_QUERY = "business analytics dashboard with rising charts and data visualizations"
STATISTICS_EXTRA_NEGATIVES = ["fabricated statistics overlays"]

# Function words dropped when extracting search keywords from narration.
# Stock providers AND-match query terms, so sentence fragments and style
# filler ("in realistic setting", "bright modern footage") degrade results.
_QUERY_STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "while",
    "at", "by", "for", "to", "of", "in", "on", "with", "from", "into", "onto",
    "over", "under", "again", "further", "once", "this", "that", "these", "those",
    "there", "here", "where", "which", "who", "whom", "whose", "what", "is", "are",
    "was", "were", "be", "been", "being", "am", "do", "does", "did", "doing",
    "done", "have", "has", "had", "having", "can", "could", "shall", "should",
    "will", "would", "may", "might", "must", "not", "no", "nor", "so", "than",
    "too", "very", "just", "only", "also", "more", "most", "some", "such", "own",
    "same", "it", "its", "they", "them", "their", "he", "she", "his", "her",
    "we", "our", "us", "you", "your", "i", "me", "my", "as", "up", "out", "off",
    "about", "how", "all", "any", "both", "each", "few", "other", "don", "doesn",
    "didn", "isn", "aren", "wasn", "weren", "won", "wouldn", "couldn", "shouldn",
}


def _scene_mentions_named_person(scene_text: str) -> bool:
    """Heuristic detection of named-person references in narration text."""
    for match in _NAMED_PERSON_PATTERN.finditer(scene_text):
        candidate = match.group(1).lower()
        if candidate.startswith("the "):
            continue
        if candidate not in _NON_PERSON_ENTITIES:
            return True
    return False


class ContextualQueryDisambiguator:
    """
    Translates raw narration phrases into disambiguated, commercially clean,
    and visually searchable B-roll queries.
    """

    def __init__(self, default_negative_constraints: Optional[List[str]] = None) -> None:
        self.default_negatives = default_negative_constraints or DEFAULT_NEGATIVE_CONSTRAINTS

    def disambiguate_scene(
        self,
        scene_text: str,
        full_context: str,
        language: str = "en",
        user_avoid_list: Optional[List[str]] = None,
        style_hint: Optional[str] = None,
        visual_hint: Optional[str] = None,
    ) -> Tuple[str, str, List[str]]:
        """
        Determines the visual search query, intent category, and negative constraints.
        Returns: (visual_query, visual_intent, negative_constraints)
        """
        # Step 0: Assemble combined negative constraints
        negatives = list(self.default_negatives)
        if user_avoid_list:
            for item in user_avoid_list:
                cleaned = item.strip().lower()
                if cleaned and cleaned not in negatives:
                    negatives.append(cleaned)

        # Step 1: If an explicit director visual hint was provided in the request, prioritize it
        if visual_hint and visual_hint.strip():
            return visual_hint.strip(), "concrete_action", negatives

        # Tokenize context for keyword matching with simple singularization support
        words_scene_raw = set(re.findall(r"\w+", scene_text.lower()))
        words_scene = words_scene_raw | {w.rstrip("s") for w in words_scene_raw if len(w) > 3}
        words_context_raw = set(re.findall(r"\w+", full_context.lower()))
        words_context = words_context_raw | {w.rstrip("s") for w in words_context_raw if len(w) > 3}

        # Step 2: Check for Homonyms & Polysemes in scene text
        for term, senses in HOMONYM_DISAMBIGUATION_MAP.items():
            if term in words_scene:
                # Score each sense based on overlap with the broader context
                best_match = None
                max_overlap = -1
                for keywords, visual_query, intent in senses:
                    overlap = len(keywords.intersection(words_context))
                    if overlap > max_overlap:
                        max_overlap = overlap
                        best_match = (visual_query, intent)

                if best_match and max_overlap > 0:
                    return best_match[0], best_match[1], negatives

        # Step 3: Check for Multilingual Concept Mappings (Hindi & Tamil)
        for term_set, visual_query, intent in MULTILINGUAL_CONCEPT_MAP:
            if term_set.intersection(words_scene) or term_set.intersection(words_context):
                return visual_query, intent, negatives

        # Step 4: Check for Abstract Concept Metaphors
        for concept_set, visual_query, intent in ABSTRACT_CONCEPT_MAP:
            if concept_set.intersection(words_scene):
                return visual_query, intent, negatives

        # Step 5: Content safety screening (named people, brands, sensitive news, statistics)
        safety_query, safety_intent, safety_negatives = self._screen_content_safety(
            scene_text=scene_text,
            words_scene=words_scene,
        )
        if safety_query:
            negatives.extend(n for n in safety_negatives if n not in negatives)
            return safety_query, safety_intent, negatives

        # Step 6: Fallback to Natural Scene Subject Query Extraction
        # Keep only content keywords — providers AND-match query terms, so raw
        # sentence fragments ("They fail when users don't") return unusable
        # result sets and everything degrades to procedural fallback.
        seen: Set[str] = set()
        keywords: List[str] = []
        for token in scene_text.split():
            w = token.strip(".,;:!?()\"'").lower()
            if len(w) <= 2 or w in _QUERY_STOPWORDS or w in seen:
                continue
            seen.add(w)
            keywords.append(w)
            if len(keywords) >= 5:
                break
        fallback_query = " ".join(keywords) if keywords else scene_text[:50].strip()

        return fallback_query, "concrete_action", negatives

    def _screen_content_safety(
        self,
        scene_text: str,
        words_scene: Set[str],
    ) -> Tuple[Optional[str], Optional[str], List[str]]:
        """Detects content requiring safe visual treatment.

        Returns (query, intent, extra_negatives) or (None, None, []) when the
        scene is unremarkable. Priority: sensitive topics > named people > brands
        > statistics.
        """
        lowered = scene_text.lower()

        # 1. Sensitive news/tragedy → respectful non-graphic metaphor
        if words_scene.intersection(SENSITIVE_TOPIC_KEYWORDS):
            return SENSITIVE_TOPIC_QUERY, "metaphor", list(SENSITIVE_TOPIC_EXTRA_NEGATIVES)

        # 2. Named real people → generic professional visual (never faces of real people)
        if _scene_mentions_named_person(scene_text):
            return NAMED_PERSON_QUERY, "concrete_action", list(NAMED_PERSON_EXTRA_NEGATIVES)

        # 3. Named brands → generic product/category visual
        for brand, generic in KNOWN_BRAND_MAP.items():
            if re.search(rf"\b{re.escape(brand)}\b", lowered):
                return (
                    f"generic {generic} product lifestyle context",
                    "concrete_action",
                    list(BRAND_EXTRA_NEGATIVES),
                )

        # 4. Statistics/numbers → data-visualization metaphor
        if _STATISTICS_PATTERN.search(scene_text):
            return STATISTICS_QUERY, "metaphor", list(STATISTICS_EXTRA_NEGATIVES)

        return None, None, []
