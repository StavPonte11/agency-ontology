"""
Entity resolver — deduplicates and merges extracted concepts against existing graph entries.
Supports Hebrew text normalization for military terms.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)

NIKUD_PATTERN = re.compile(r"[\u05B0-\u05C7]")
GERESH_PATTERN = re.compile(r'[״"]')   # Hebrew geresh/gershayim in abbreviations


def normalize_hebrew_term(text: str) -> str:
    """Normalize a Hebrew term for comparison: strip nikud, lowercase, strip punctuation."""
    text = NIKUD_PATTERN.sub("", text)
    text = GERESH_PATTERN.sub("", text)
    text = unicodedata.normalize("NFC", text)
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_english_term(text: str) -> str:
    """Normalize an English term for comparison."""
    return text.lower().strip().replace("-", " ").replace("_", " ")


def normalize_term(text: str) -> str:
    """Auto-detect language and normalize."""
    has_hebrew = bool(re.search(r"[\u05D0-\u05EA]", text))
    if has_hebrew:
        return normalize_hebrew_term(text)
    return normalize_english_term(text)


def similarity_score(a: str, b: str) -> float:
    """Compute string similarity score 0.0–1.0."""
    a_norm = normalize_term(a)
    b_norm = normalize_term(b)
    if a_norm == b_norm:
        return 1.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


class EntityResolver:
    """
    Resolves extracted concept names against existing graph entries.
    Prevents duplicates by matching:
    1. Exact normalized match (same term)
    2. Fuzzy match above threshold (likely alias or typo)
    3. Semantic match (via Elasticsearch embedding — handled by caller)
    """

    EXACT_THRESHOLD = 1.0
    FUZZY_THRESHOLD = 0.88   # High threshold for military terminology (don't merge different units)

    def __init__(self) -> None:
        self._known_names: dict[str, str] = {}   # normalized_name → concept_id

    def register(self, concept_name: str, concept_id: str) -> None:
        """Register a known concept name → ID mapping."""
        logger.info(f"Registering concept: '{concept_name}' (id={concept_id})")
        self._known_names[normalize_term(concept_name)] = concept_id

    def resolve(self, candidate_name: str) -> Optional[str]:
        """
        Attempt to resolve a candidate concept name to an existing concept ID.
        Returns concept_id if match found, None if new concept.
        """
        normalized = normalize_term(candidate_name)

        # Exact match
        if normalized in self._known_names:
            return self._known_names[normalized]

        # Fuzzy match
        for known_norm, concept_id in self._known_names.items():
            score = similarity_score(normalized, known_norm)
            if score >= self.FUZZY_THRESHOLD:
                logger.info(
                    f"Resolved: '{candidate_name}' → existing concept {concept_id} (fuzzy score={score:.2f})"
                )
                return concept_id

        return None

    def is_duplicate(self, name_a: str, name_b: str) -> bool:
        return similarity_score(name_a, name_b) >= self.FUZZY_THRESHOLD
