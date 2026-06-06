# -*- coding: utf-8 -*-

import json

from agents.llm_client import (
    DeepSeekChatClient,
    DryRunLLMClient,
    default_model_for_provider,
    first_json_field,
    parse_chat_completion_json,
    parse_response_json,
)


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


def test_parse_chat_completion_json_reads_message_content():
    body = {
        "choices": [
            {"message": {"content": "```json\n{\"ok\": true}\n```"}}
        ]
    }

    assert parse_chat_completion_json(body) == {"ok": True}


def test_deepseek_client_uses_env_key_and_base_url(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.test/v1/")

    client = DeepSeekChatClient()

    assert client.api_url == "https://example.test/v1/chat/completions"
    assert default_model_for_provider("deepseek") == "deepseek-v4-flash"
