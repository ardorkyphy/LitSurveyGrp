# -*- coding: utf-8 -*-
"""Validation helpers for structured agent outputs."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


def validate_schema(data: Any, schema: dict, path: str = "$") -> list[str]:
    """Validate a small JSON-schema subset used by the agent contracts."""
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type and not _matches_type(data, expected_type):
        errors.append(f"{path}: expected {expected_type}, got {type(data).__name__}")
        return errors

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: expected one of {schema['enum']}, got {data!r}")

    if expected_type == "object":
        if not isinstance(data, dict):
            return errors
        properties = schema.get("properties") or {}
        for key in schema.get("required") or []:
            if key not in data:
                errors.append(f"{path}.{key}: missing required field")
        if schema.get("additionalProperties") is False:
            for key in data:
                if key not in properties:
                    errors.append(f"{path}.{key}: unexpected field")
        for key, subschema in properties.items():
            if key in data:
                errors.extend(validate_schema(data[key], subschema, f"{path}.{key}"))

    if expected_type == "array":
        if not isinstance(data, list):
            return errors
        item_schema = schema.get("items") or {}
        for index, item in enumerate(data):
            errors.extend(validate_schema(item, item_schema, f"{path}[{index}]"))

    return errors


def require_non_empty_strings(data: dict, keys: list[str]) -> list[str]:
    errors = []
    for key in keys:
        if not isinstance(data.get(key), str) or not data.get(key, "").strip():
            errors.append(f"$.{key}: must be a non-empty string")
    return errors


def unsupported_supporting_text(data: dict, basis_text: str, min_ratio: float = 0.92) -> list[str]:
    """Return supporting snippets that are not grounded in supplied text."""
    snippets = data.get("supporting_text") or []
    if not isinstance(snippets, list):
        return []
    source = normalize_text(basis_text)
    if not source:
        return [str(item) for item in snippets if str(item).strip()]
    unsupported = []
    for item in snippets:
        snippet = str(item).strip()
        if not snippet:
            continue
        normalized = normalize_text(snippet)
        if normalized in source:
            continue
        if best_window_ratio(normalized, source) >= min_ratio:
            continue
        unsupported.append(snippet)
    return unsupported


def unknown_evidence_papers(synthesis: dict, known_titles: set[str]) -> list[str]:
    unknown = []
    normalized_titles = {normalize_title(title) for title in known_titles if title}
    for item in synthesis.get("evidence_index") or []:
        if not isinstance(item, dict):
            continue
        for title in item.get("papers") or []:
            if normalize_title(str(title)) not in normalized_titles:
                unknown.append(str(title))
    return unknown


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).casefold()).strip()


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(title).casefold()).strip()


def best_window_ratio(snippet: str, source: str) -> float:
    if not snippet or not source:
        return 0.0
    if len(snippet) > len(source):
        return SequenceMatcher(None, snippet, source).ratio()
    window_size = max(len(snippet), 1)
    step = max(window_size // 4, 1)
    best = 0.0
    for start in range(0, max(len(source) - window_size + 1, 1), step):
        window = source[start : start + window_size]
        best = max(best, SequenceMatcher(None, snippet, window).ratio())
        if best >= 0.99:
            break
    return best


def _matches_type(data: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(data, dict)
    if expected_type == "array":
        return isinstance(data, list)
    if expected_type == "string":
        return isinstance(data, str)
    if expected_type == "number":
        return isinstance(data, (int, float)) and not isinstance(data, bool)
    if expected_type == "integer":
        return isinstance(data, int) and not isinstance(data, bool)
    if expected_type == "boolean":
        return isinstance(data, bool)
    if expected_type == "null":
        return data is None
    return True
