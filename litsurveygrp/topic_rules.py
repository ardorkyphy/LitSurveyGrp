# -*- coding: utf-8 -*-
"""Load transparent local topic rules from JSON presets or files."""

import json
from pathlib import Path

from litsurveygrp.paper_classifier import DomainRule


def load_domain_rules(value: str | Path | None) -> list[DomainRule] | None:
    """Return user-supplied domain rules from a JSON file."""
    if not value:
        return None
    text = str(value).strip()
    path = Path(text)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        data = data.get("rules", [])
    rules = []
    for item in data or []:
        domain = str(item.get("domain", "")).strip()
        terms = [str(term).strip() for term in (item.get("terms") or []) if str(term).strip()]
        if domain and terms:
            rules.append(DomainRule(domain, terms))
    return rules
