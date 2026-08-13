import json
import re

from router import ModelRouter


class MemoryConsolidator:
    """
    Uses an LLM to reconcile new meeting findings
    with the existing project memory.
    """

    def __init__(self, router=None):
        self.router = router or ModelRouter()

    def build_prompt(self, existing_memory, new_analysis):
        """
        Build the prompt used to consolidate project memory.
        """

        return f"""
You are an AI project memory manager.

Your task is to reconcile NEW meeting findings with EXISTING project memory.

The goal is to maintain one canonical representation of the current
project state while preserving important changes and avoiding duplicates.

You must analyze these memory categories:

- risks
- blockers
- action_items
- decisions

For each new item, determine whether it should be:

- CREATE — genuinely new information
- MERGE — same meaning as an existing item, even if wording is different
- UPDATE — same underlying item but with changed information
- CONFLICT — the new information contradicts existing information

Important rules:

1. Compare meaning, not exact wording.
2. Different wording does NOT necessarily mean a different item.
3. Do not merge items merely because they are related.
4. Do not mark an item as completed or resolved unless the new meeting explicitly
   says that it was completed or resolved.
5. If a new item contains additional information about an existing item,
   prefer UPDATE rather than CREATE.
6. If the new information contradicts existing information, use CONFLICT.
7. Preserve the identity of existing items by referring to their IDs.
8. Do not invent IDs.
9. Do not delete existing memory directly. MERGE decisions will be handled
   by the application.
10. Return only valid JSON. Do not use Markdown fences or commentary.

Return exactly this structure:

{{
  "risks": [
    {{
      "decision": "CREATE|MERGE|UPDATE|CONFLICT",
      "new_item": {{
        "title": "string",
        "description": "string",
        "impact": "low|medium|high|unknown",
        "mitigation": "string",
        "status": "open|resolved"
      }},
      "existing_item_id": null,
      "canonical_title": "string",
      "reason": "string"
    }}
  ],

  "blockers": [
    {{
      "decision": "CREATE|MERGE|UPDATE|CONFLICT",
      "new_item": {{
        "title": "string",
        "description": "string",
        "status": "open|resolved"
      }},
      "existing_item_id": null,
      "canonical_title": "string",
      "reason": "string"
    }}
  ],

  "action_items": [
    {{
      "decision": "CREATE|MERGE|UPDATE|CONFLICT",
      "new_item": {{
        "title": "string",
        "details": "string",
        "owner": "string",
        "due_date": "YYYY-MM-DD or null",
        "status": "open|completed"
      }},
      "existing_item_id": null,
      "canonical_title": "string",
      "reason": "string"
    }}
  ],

  "decisions": [
    {{
      "decision": "CREATE|MERGE|UPDATE|CONFLICT",
      "new_item": {{
        "title": "string",
        "details": "string"
      }},
      "existing_item_id": null,
      "canonical_title": "string",
      "reason": "string"
    }}
  ]
}}

EXISTING PROJECT MEMORY:

{json.dumps(existing_memory, indent=2, ensure_ascii=False)}

NEW MEETING FINDINGS:

{json.dumps(new_analysis, indent=2, ensure_ascii=False)}
"""

    def consolidate(
        self,
        existing_memory,
        new_analysis,
        provider,
        model,
    ):
        """
        Compare new meeting findings with existing project memory.

        Returns:
            dict: AI-generated consolidation plan.
        """

        prompt = self.build_prompt(
            existing_memory=existing_memory,
            new_analysis=new_analysis,
        )

        result = self.router.generate(
            provider=provider,
            model=model,
            prompt=prompt,
        )

        return self.parse_result(result)

    @staticmethod
    def parse_result(result):
        """
        Parse and validate the AI consolidation response.
        """

        cleaned = result.strip()

        fenced = re.fullmatch(
            r"```(?:json)?\s*(.*?)\s*```",
            cleaned,
            re.DOTALL,
        )

        if fenced:
            cleaned = fenced.group(1)

        try:
            consolidation = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise ValueError(
                "The AI memory consolidation response "
                "was not valid structured JSON."
            ) from error

        if not isinstance(consolidation, dict):
            raise ValueError(
                "The AI memory consolidation response "
                "must be a JSON object."
            )

        required_sections = (
            "risks",
            "blockers",
            "action_items",
            "decisions",
        )

        for section in required_sections:
            if section not in consolidation:
                consolidation[section] = []

            if not isinstance(consolidation[section], list):
                raise ValueError(
                    f"Invalid consolidation section: {section}"
                )

        return consolidation