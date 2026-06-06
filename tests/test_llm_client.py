# -*- coding: utf-8 -*-

import json

from agents.llm_client import DryRunLLMClient, first_json_field, parse_response_json


def test_first_json_field_finds_nested_values():
    payload = {
        "paper": {
            "title": "Nested Paper",
            "domain": "Methods > Evaluation",
        }
    }

    assert first_json_field(json.dumps(payload), "title") == "Nested Paper"
    assert first_json_field(json.dumps(payload), "domain") == "Methods > Evaluation"


def test_dry_run_client_returns_paper_schema_output():
    client = DryRunLLMClient()
    result = client.complete_json(
        system="",
        user=json.dumps({"paper": {"title": "A Paper", "domain": "A Domain"}}),
        schema={"properties": {"research_problem": {"type": "string"}}},
        model="dry",
        cache_key="x",
    )

    assert result["research_problem"].endswith("A Paper.")
    assert result["study_object"] == "A Domain"
    assert result["confidence"] == "low"


def test_parse_response_json_reads_responses_output_text():
    body = {
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": "{\"ok\": true}",
                    }
                ]
            }
        ]
    }

    assert parse_response_json(body) == {"ok": True}
