"""Unit tests for Groq retry correction messages."""

from __future__ import annotations

import unittest

from compact_prompt_tune.self_improve.groq_client import (
    _build_correction_message,
    _describe_invalid_output,
    _extract_validation_detail,
)
from compact_prompt_tune.self_improve.prompts import patch_schema_for_section


class ExtractValidationDetailTests(unittest.TestCase):
    def test_pulls_jsonschema_line(self) -> None:
        msg = (
            "Groq HTTP 400: Generated JSON does not match the expected schema. "
            "Error: jsonschema: '' does not validate with /required: missing properties: 'content'"
        )
        self.assertIn("missing properties: 'content'", _extract_validation_detail(msg))

    def test_falls_back_to_full_message(self) -> None:
        self.assertEqual("empty content", _extract_validation_detail("empty content"))


class DescribeInvalidOutputTests(unittest.TestCase):
    def test_lists_missing_and_unexpected_keys(self) -> None:
        schema = patch_schema_for_section("domain.compact_rules")
        required = schema["required"]
        allowed = list(schema["properties"].keys())
        failed = (
            '{"target_section":"domain.compact_rules","operation":"replace",'
            '"add":[],"remove_texts":[],"rationale":"x","expected_fixes":[],"risk":"low"}'
        )
        summary = _describe_invalid_output(
            failed,
            required_keys=required,
            allowed_keys=allowed,
        )
        assert summary is not None
        self.assertIn("Missing required keys: content", summary)
        self.assertIn("Unexpected keys", summary)
        self.assertIn("add", summary)


class BuildCorrectionMessageTests(unittest.TestCase):
    def test_includes_schema_requirements_and_failure_detail(self) -> None:
        schema = patch_schema_for_section("domain.compact_rules")
        failed = (
            '{"target_section":"domain.compact_rules","operation":"replace",'
            '"add":[],"remove_texts":[],"rationale":"x","expected_fixes":[],"risk":"low"}'
        )
        message = _build_correction_message(
            schema_name="patch_domain_compact_rules",
            response_schema=schema,
            error_message=(
                "Groq HTTP 400: schema mismatch. "
                "Error: jsonschema: '' does not validate with /required: missing properties: 'content'"
            ),
            failed_generation=failed,
        )
        self.assertIn("What broke:", message)
        self.assertIn("missing properties: 'content'", message)
        self.assertIn("Required keys:", message)
        self.assertIn("content", message)
        self.assertIn("Missing required keys: content", message)
        self.assertIn("operation: always \"replace\"", message)
        self.assertIn("content: full replacement compact_rules text", message)


if __name__ == "__main__":
    unittest.main()
