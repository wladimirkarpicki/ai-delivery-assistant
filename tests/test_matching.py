import unittest

from matching import (
    ALL_SECTIONS,
    combine_plans,
    downgrade_create_duplicates,
    has_llm_findings,
    normalize_title,
    pre_match,
    similarity,
    title_tokens,
)

MEMORY = {
    "risks": [
        {"id": 1, "title": "QA capacity", "status": "open"},
        {"id": 2, "title": "API instability in staging", "status": "open"},
    ],
    "blockers": [
        {"id": 3, "title": "Pending security review", "status": "open"},
    ],
    "action_items": [
        {"id": 4, "title": "Find QA support", "status": "open"},
    ],
    "decisions": [
        {"id": 5, "title": "Adopt flow", "status": "open"},
    ],
}


class NormalizeTests(unittest.TestCase):
    def test_normalize_title(self):
        self.assertEqual(normalize_title("  QA   Capacity! "), "qa capacity")
        self.assertEqual(normalize_title('   "Release: go-live"   '), "release: go-live")
        self.assertEqual(normalize_title(None), "")
        self.assertEqual(normalize_title(42), "")

    def test_similarity_orders_candidates(self):
        tokens = title_tokens("QA capacity problem")
        near = similarity(tokens, title_tokens("QA capacity"))
        far = similarity(tokens, title_tokens("capacity of the team"))
        self.assertGreater(near, far)


class PreMatchTests(unittest.TestCase):
    def test_exact_duplicate_auto_merged(self):
        result = pre_match(
            MEMORY,
            {"risks": [{"title": "qa capacity", "status": "open"}]},
        )

        entry = result["auto"]["risks"][0]
        self.assertEqual(entry["decision"], "MERGE")
        self.assertEqual(entry["existing_item_id"], 1)
        self.assertEqual(result["llm_findings"]["risks"], [])

    def test_status_flip_auto_updated(self):
        result = pre_match(
            MEMORY,
            {
                "risks": [
                    {
                        "title": "QA Capacity",
                        "status": "resolved",
                        "description": "Support assigned",
                    }
                ]
            },
        )

        entry = result["auto"]["risks"][0]
        self.assertEqual(entry["decision"], "UPDATE")
        self.assertEqual(entry["existing_item_id"], 1)
        self.assertEqual(entry["new_item"]["status"], "resolved")
        self.assertEqual(entry["new_item"]["description"], "Support assigned")

    def test_action_status_flip_maps_to_completed(self):
        result = pre_match(
            MEMORY,
            {
                "action_items": [
                    {"title": "Find QA support", "status": "completed"}
                ]
            },
        )

        entry = result["auto"]["action_items"][0]
        self.assertEqual(entry["decision"], "UPDATE")
        self.assertEqual(entry["new_item"]["status"], "completed")

    def test_decisions_are_never_auto_resolved(self):
        result = pre_match(
            MEMORY,
            {"decisions": [{"title": "Adopt flow", "details": "d"}]},
        )

        self.assertNotIn("decisions", result["auto"])

        # The duplicate decision goes to the LLM with its candidate.
        finding = result["llm_findings"]["decisions"][0]
        self.assertEqual(finding["candidate_ids"], [5])

    def test_unmatched_finding_gets_empty_candidates(self):
        result = pre_match(
            MEMORY,
            {"risks": [{"title": "New compliance risk", "status": "open"}]},
        )

        finding = result["llm_findings"]["risks"][0]
        self.assertEqual(finding["candidate_ids"], [])

    def test_candidate_ordering_best_similarity_first(self):
        result = pre_match(
            MEMORY,
            {"risks": [{"title": "QA capacity problem", "status": "open"}]},
        )

        candidates = result["llm_findings"]["risks"][0]["candidate_ids"]
        self.assertEqual(candidates[0], 1)

    def test_original_analysis_is_not_mutated(self):
        analysis = {
            "risks": [{"title": "QA capacity", "status": "open", "note": "x"}]
        }

        pre_match(MEMORY, analysis)

        self.assertNotIn("candidate_ids", analysis["risks"][0])

    def test_same_title_findings_within_one_meeting_collapsed(self):
        result = pre_match(
            {},
            {
                "risks": [
                    {"title": "QA capacity", "status": "open", "description": "first"},
                    {"title": "QA Capacity!", "status": "open", "description": "second"},
                ]
            },
        )

        # One finding survives; the first mention wins.
        self.assertEqual(len(result["llm_findings"]["risks"]), 1)
        self.assertEqual(result["llm_findings"]["risks"][0]["description"], "first")

    def test_status_flip_within_one_meeting_wins(self):
        result = pre_match(
            {},
            {
                "risks": [
                    {"title": "QA capacity", "status": "open"},
                    {"title": "QA capacity", "status": "resolved"},
                ]
            },
        )

        self.assertEqual(len(result["llm_findings"]["risks"]), 1)
        self.assertEqual(result["llm_findings"]["risks"][0]["status"], "resolved")

    def test_has_llm_findings(self):
        empty = {section: [] for section in ALL_SECTIONS}
        self.assertFalse(has_llm_findings(empty))
        self.assertFalse(has_llm_findings({}))
        self.assertTrue(
            has_llm_findings({**empty, "decisions": [{"title": "x"}]})
        )


class DowngradeTests(unittest.TestCase):
    def test_create_duplicate_downgraded_to_merge(self):
        plan = {
            "risks": [
                {
                    "decision": "CREATE",
                    "new_item": {"title": "QA capacity", "status": "open"},
                    "reason": "llm missed the existing item",
                }
            ]
        }

        count = downgrade_create_duplicates(MEMORY, plan)

        self.assertEqual(count, 1)
        self.assertEqual(plan["risks"][0]["decision"], "MERGE")
        self.assertEqual(plan["risks"][0]["existing_item_id"], 1)

    def test_create_unique_is_kept(self):
        plan = {
            "risks": [
                {
                    "decision": "CREATE",
                    "new_item": {"title": "Brand new risk", "status": "open"},
                }
            ]
        }

        self.assertEqual(downgrade_create_duplicates(MEMORY, plan), 0)
        self.assertEqual(plan["risks"][0]["decision"], "CREATE")

    def test_combine_plans_merges_sections(self):
        combined = combine_plans(
            {
                "risks": [
                    {
                        "decision": "MERGE",
                        "existing_item_id": 1,
                        "new_item": {"title": "QA capacity"},
                    }
                ]
            },
            {
                "risks": [
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "New risk"},
                    }
                ],
                "decisions": [
                    {
                        "decision": "CREATE",
                        "new_item": {"title": "D"},
                    }
                ],
            },
        )

        self.assertEqual(len(combined["risks"]), 2)
        self.assertEqual(combined["blockers"], [])
        self.assertEqual(
            combined["decisions"],
            [{"decision": "CREATE", "new_item": {"title": "D"}}],
        )


if __name__ == "__main__":
    unittest.main()
