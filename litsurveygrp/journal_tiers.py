# -*- coding: utf-8 -*-
"""Conservative journal tier scoring used by research ranking."""


DEFAULT_JOURNAL_TIER_MAP = {
    "nature": ("top_general", 1.0),
    "science": ("top_general", 1.0),
    "cell": ("top_general", 1.0),
    "new england journal of medicine": ("top_medical", 1.0),
    "the lancet": ("top_medical", 1.0),
    "jama": ("top_medical", 0.95),
    "nature medicine": ("top_field", 0.92),
    "nature biotechnology": ("top_field", 0.92),
    "nature aging": ("top_field", 0.86),
    "nature neuroscience": ("top_field", 0.88),
    "nature genetics": ("top_field", 0.88),
    "pnas": ("high_impact", 0.82),
    "proceedings of the national academy of sciences": ("high_impact", 0.82),
    "elife": ("high_impact", 0.76),
    "aging cell": ("field_journal", 0.72),
    "geroscience": ("field_journal", 0.68),
    "ieee transactions on pattern analysis and machine intelligence": ("top_field", 0.9),
    "international journal of computer vision": ("top_field", 0.82),
}


class JournalTierScorer:
    """Assign a conservative journal tier score."""

    def __init__(self, tier_map: dict[str, tuple[str, float]] | None = None, default_score: float = 0.45):
        self.tier_map = tier_map or dict(DEFAULT_JOURNAL_TIER_MAP)
        self.default_score = default_score

    def score(self, journal: str) -> tuple[str, float]:
        key = normalize(journal)
        if key in self.tier_map:
            return self.tier_map[key]
        for name, tier in self.tier_map.items():
            if key and (name in key or key in name):
                return tier
        return ("unmapped", self.default_score)


def normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())
