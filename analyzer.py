from router import ModelRouter


def build_prompt(text):
    """
    Build prompt for meeting analysis.
    """

    return f"""
You are an experienced Delivery Manager.

Analyze the meeting notes below.

Provide a structured delivery analysis:

## Executive Summary

Summarize the key discussion points.

## Project Status

Describe:
- current progress
- completed items
- items in progress

## Risks

List all identified risks.
Include impact and mitigation if available.

## Blockers

List all blockers preventing progress.

## Decisions Made

List important decisions.

## Action Items

For each action item provide:
- task
- owner
- deadline (if mentioned)

Meeting Notes:

{text}
"""



def analyze_document(
        text,
        provider,
        model,
        router_instance=None,
):
    """
    Analyze meeting notes using selected AI provider.

    Args:
        text (str): meeting notes
        provider (str): provider name (google/groq)
        model (str): selected model

    Returns:
        str: AI response
    """

    prompt = build_prompt(text)


    router = router_instance or ModelRouter()

    result = router.generate(
        provider=provider,
        model=model,
        prompt=prompt
    )


    return result
