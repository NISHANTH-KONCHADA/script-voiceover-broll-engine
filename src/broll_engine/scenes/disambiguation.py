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
            hint_clean = visual_hint.strip()
            # Still append style if specified
            if style_hint and "real-world" not in hint_clean:
                query = f"{hint_clean}, {style_hint}"
            else:
                query = hint_clean
            return query, "concrete_action", negatives

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
                    query = best_match[0]
                    if style_hint and "style" not in query:
                        query = f"{query}, {style_hint}"
                    return query, best_match[1], negatives

        # Step 3: Check for Multilingual Concept Mappings (Hindi & Tamil)
        for term_set, visual_query, intent in MULTILINGUAL_CONCEPT_MAP:
            if term_set.intersection(words_scene) or term_set.intersection(words_context):
                query = visual_query
                if style_hint:
                    query = f"{query}, {style_hint}"
                return query, intent, negatives

        # Step 4: Check for Abstract Concept Metaphors
        for concept_set, visual_query, intent in ABSTRACT_CONCEPT_MAP:
            if concept_set.intersection(words_scene):
                query = visual_query
                if style_hint:
                    query = f"{query}, {style_hint}"
                return query, intent, negatives

        # Step 5: Fallback to Natural Scene Subject Query Extraction
        # Extract meaningful nouns, verbs, and clean narrative elements
        cleaned_words = [w for w in scene_text.split() if len(w) > 3 and w.lower() not in {
            "this", "that", "these", "those", "with", "from", "into", "during", "before", "after",
            "above", "below", "between", "under", "again", "further", "then", "once", "here", "there"
        }]
        core_phrase = " ".join(cleaned_words[:6]) if cleaned_words else scene_text[:50]
        fallback_query = f"{core_phrase} in realistic setting"
        if style_hint:
            fallback_query = f"{fallback_query}, {style_hint}"

        return fallback_query, "concrete_action", negatives
