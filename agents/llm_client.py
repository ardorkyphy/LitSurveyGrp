# -*- coding: utf-8 -*-
"""Small replaceable LLM client used by research agents."""

import hashlib
import json
import os
import time
from pathlib import Path
from urllib import request


class LLMError(RuntimeError):
    pass


class LLMClient:
    def complete_json(self, *, system: str, user: str, schema: dict, model: str, cache_key: str) -> dict:
        raise NotImplementedError


class DryRunLLMClient(LLMClient):
    """Deterministic offline client for smoke tests and pipeline dry runs."""

    def complete_json(self, *, system: str, user: str, schema: dict, model: str, cache_key: str) -> dict:
        title = first_json_field(user, "title") or "Untitled"
        domain = first_json_field(user, "domain") or first_json_field(user, "domain_name") or "Unknown"
        source_basis = first_json_field(user, "source_basis") or "metadata_only"
        if source_basis not in {"metadata_only", "abstract_only", "pdf_text"}:
            source_basis = "metadata_only"
        if "research_problem" in schema.get("properties", {}):
            return {
                "research_problem": f"Clarify the central research question of {title}.",
                "background_gap": "Insufficient evidence in the provided input.",
                "study_object": domain,
                "data_or_materials": [],
                "methods": [],
                "method_pipeline": "",
                "core_findings": [],
                "evidence_type": "unknown",
                "limitations": ["Dry-run output; no model analysis was performed."],
                "open_questions": [],
                "reusable_resources": [],
                "source_basis": source_basis,
                "confidence": "low",
                "supporting_text": [],
            }
        return {
            "domain": domain,
            "one_sentence_summary": f"Dry-run synthesis for {domain}.",
            "core_problem_system": [],
            "method_system": [],
            "problem_method_matrix": [],
            "mature_findings": [],
            "controversies_or_uncertainties": [],
            "research_gaps": [],
            "recommended_reading_order": [],
            "candidate_research_questions": [],
            "evidence_index": [],
            "confidence": "low",
        }


class CachedLLMClient(LLMClient):
    def __init__(self, inner: LLMClient, cache_dir: Path):
        self.inner = inner
        self.cache_dir = Path(cache_dir)

    def complete_json(self, *, system: str, user: str, schema: dict, model: str, cache_key: str) -> dict:
        key = hashlib.sha256("|".join([model, cache_key, system, user]).encode("utf-8")).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        result = self.inner.complete_json(system=system, user=user, schema=schema, model=model, cache_key=cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result


class OpenAIResponsesClient(LLMClient):
    """Minimal OpenAI Responses API client using stdlib urllib."""

    API_URL = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str | None = None, timeout: int = 120, max_retries: int = 2):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is required for OpenAIResponsesClient")

    def complete_json(self, *, system: str, user: str, schema: dict, model: str, cache_key: str) -> dict:
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "research_agent_output",
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        data = json.dumps(payload).encode("utf-8")
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                req = request.Request(
                    self.API_URL,
                    data=data,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with request.urlopen(req, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                return parse_response_json(body)
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
        raise LLMError(f"OpenAI request failed: {last_error}")


def parse_response_json(body: dict) -> dict:
    for item in body.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                return json.loads(content["text"])
    text = body.get("output_text")
    if text:
        return json.loads(text)
    raise LLMError("No JSON text found in Responses API output")


def build_llm_client(provider: str = "openai", cache_dir: Path | None = None) -> LLMClient:
    if provider == "dry-run":
        client: LLMClient = DryRunLLMClient()
    elif provider == "openai":
        client = OpenAIResponsesClient()
    else:
        raise LLMError(f"unsupported LLM provider: {provider}")
    if cache_dir:
        client = CachedLLMClient(client, cache_dir)
    return client


def first_json_field(text: str, field: str) -> str:
    try:
        data = json.loads(text)
    except Exception:
        return ""
    value = find_field(data, field)
    if isinstance(value, str):
        return value
    return ""


def find_field(value, field: str):
    if isinstance(value, dict):
        if field in value:
            return value[field]
        for item in value.values():
            found = find_field(item, field)
            if found not in (None, ""):
                return found
    if isinstance(value, list):
        for item in value:
            found = find_field(item, field)
            if found not in (None, ""):
                return found
    return None
