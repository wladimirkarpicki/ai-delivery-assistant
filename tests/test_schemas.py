import json
import unittest

from analyzer import parse_analysis
from memory_consolidator import MemoryConsolidator
from services.schema_models import (
    validate_analysis,
    validate_consolidation_plan,
)


class SchemaValidationTests(unittest.TestCase):
    def test_valid_analysis_passes(self):
        validate_analysis(
            {
                "executive_summary": "ok",
                "project_status": "on_track",
                "progress_summary": "p",
                "completed_items": ["a"],
                "in_progress_items": [],
                "risks": [
                    {
                        "title": "QA capacity",
                        "status": "open",
                        "unknown_extra_key": "ignored",
                    }
                ],
                "blockers": [],
                "decisions": [],
                "action_items": [
                    {"title": "Task", "due_date": "2026-08-15"}
                ],
            }
        )

    def test_analysis_with_null_sections_passes(self):
        # Null sections are tolerated: the reconciliation layer already
        # treats them as empty lists.
        validate_analysis({"risks": None, "action_items": None})

    def test_analysis_with_non_dict_item_fails(self):
        with self.assertRaises(ValueError):
            validate_analysis({"risks": ["QA capacity"]})

    def test_analysis_with_non_list_section_fails(self):
        with self.assertRaises(ValueError):
            validate_analysis({"risks": {"title": "x"}})

    def test_parse_analysis_validates_schema(self):
        with self.assertRaises(ValueError):
            parse_analysis(json.dumps({"risks": ["flat string"]}))

    def test_valid_plan_passes(self):
        validate_consolidation_plan(
            {
                "risks": [
                    {
                        "decision": "UPDATE",
                        "existing_item_id": 3,
                        "new_item": {
                            "title": "QA capacity",
                            "status": "resolved",
                        },
                        "canonical_title": "QA capacity",
                        "reason": "resolved in meeting",
                    }
                ],
                "blockers": [],
                "action_items": [],
                "decisions": [],
            }
        )

    def test_plan_with_missing_sections_passes(self):
        validate_consolidation_plan({})

    def test_plan_with_null_section_fails(self):
        with self.assertRaises(ValueError):
            validate_consolidation_plan({"risks": None})

    def test_plan_with_string_entry_fails(self):
        with self.assertRaises(ValueError):
            validate_consolidation_plan({"risks": ["oops"]})

    def test_parse_result_validates_schema(self):
        with self.assertRaises(ValueError):
            MemoryConsolidator.parse_result(json.dumps({"risks": "nope"}))


if __name__ == "__main__":
    unittest.main()
