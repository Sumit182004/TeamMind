import json
import os
from pathlib import Path

from dotenv import load_dotenv
from lyzr import Studio

load_dotenv(Path(__file__).resolve().parent / ".env")

api_key = os.getenv("LYZR_API_KEY")

if not api_key:
    raise RuntimeError("LYZR_API_KEY is missing from backend/.env")

studio = Studio(api_key=api_key)



AGENTS = {
    "Researcher": {
        "role": "Decision Researcher",
        "goal": "Identify options, trade-offs, and missing information.",
        "instructions": """
Analyze the decision and its options using ALL supplied context, especially
relevant_past_memories.

MEMORY-USE REQUIREMENTS:
- Read each supplied memory's document/text/content and metadata where present.
- Extract every memory fact relevant to this decision and state it explicitly.
- Preserve the values and wording as recorded (for example, budget, deadline,
  and technology). Do not say a fact is unknown if it appears in a supplied memory.
- Label these as previously recorded facts; do not claim they are still current
  unless the supplied context establishes that.
- If memories conflict, report the conflict and dates/sources when available.
- If no supplied memory supports a detail, label that detail unknown instead
  of guessing.

Separate facts from assumptions. Identify trade-offs and missing information.
Do not invent sources or claim external research was performed.
Return a clear, structured analysis that includes a section called
"Relevant facts retrieved from memory".
""",
    },
    "Analyst": {
        "role": "Decision Analyst",
        "goal": "Compare alternatives using the available context.",
        "instructions": """
        Compare every supplied option using the same criteria:
        - Development speed and feasibility
        - Maintainability
        - Scalability
        - AI integration
        - Cost and risks

        Prioritize the user's explicitly stated requirements.
        Do not assume the team is more familiar with Python,
        JavaScript, or any other technology unless the context
        or retrieved memories support that assumption.

        Use relevant past memories as previously recorded facts.
        Distinguish facts from assumptions and unknown information.
        Do not invent scores, benchmarks, costs, or team skills.

        Explain the advantages and disadvantages of every option.
        Select a provisional leading option and explain why it best
        matches the stated priorities. State what information could
        change the recommendation.
        """,
    },
    "Dissent Engine": {
        "role": "Critical Decision Reviewer",
        "goal": "Challenge the provisional leading option.",
        "instructions": """
You must critically challenge the provisional leading option.
Identify hidden assumptions, realistic failure scenarios,
opportunity costs, and reasons another option might be better.
Use the provided research and analysis.
Do not disagree merely for the sake of disagreement.
Identify what evidence would change your assessment.
""",
    },
    "Verifier": {
        "role": "Evidence and Claim Reviewer",
        "goal": "Identify unsupported claims and unresolved uncertainty.",
        "instructions": """
Review the supplied decision context, relevant_past_memories, research,
analysis, and dissent.
Check whether relevant facts from retrieved memories were accurately carried
through the analysis and report. A fact explicitly present in a supplied memory
is supported as a previously recorded fact; do not label it unknown merely
because it has not been independently verified. Separately state whether its
current validity is unconfirmed.
Distinguish supported claims from assumptions or claims requiring external
verification. Do not claim independent verification without evidence.
Flag omitted memory facts, contradictions, missing information, and disagreements.
""",
    },
    "Synthesizer": {
        "role": "Decision Synthesis Specialist",
        "goal": "Produce a balanced, evidence-aware decision report.",
        "instructions": """
        Create a balanced decision report using the decision context
        and all preceding agent outputs.

        First inspect decision.relevant_past_memories directly.
        Include relevant recorded facts and distinguish them from
        assumptions. Never invent missing details or treat an
        unverified current status as a confirmed fact.

        The recommendation must follow the user's stated priorities
        and the Analyst's comparison of the supplied options.
        Do not assume technology familiarity or requirements that
        the user has not provided.

        Include these sections:
        1. Recommendation and reasoning
        2. Comparison of all alternatives
        3. Benefits and trade-offs
        4. Strongest counterargument
        5. Evidence gaps and uncertainties
        6. Practical next steps
        7. Stress-test scenarios and their results
        8. Vulnerabilities and mitigations
        9. Decision triggers
        10. Overall assessment

        Use the Stress Tester output explicitly.
        Preserve its scenarios, severity, mitigations, and decision
        triggers. Parse its JSON when possible instead of displaying
        raw JSON inside the report.

        Do not invent confidence scores, probabilities, costs,
        benchmarks, or claims of external verification.
        Do not hide disagreements between agents.

        Return a clear, structured report. Ensure the recommendation
        does not contradict the supplied decision context or
        relevant retrieved memories.
        """,
    },

    "Stress Tester": {
        "role": "Decision Stress Test Specialist",
        "goal": "Test the leading decision against adverse scenarios and identify when it could fail.",
        "instructions":"""
        You are TeamMind's Decision Stress Tester.

        Evaluate the provisional leading option against realistic adverse
        scenarios using the supplied decision and agent outputs.

        Return valid JSON with these keys:
        {
        "overall_assessment": "Short qualitative assessment",
        "scenarios": [
            {
            "name": "Scenario name",
            "condition": "What changes or goes wrong",
            "impact": "Likely effect on the leading option",
            "severity": "Low, Medium, or High, with explanation",
            "mitigation": "Practical action to reduce the risk",
            "decision_trigger": "Condition that would make another option preferable"
            }
        ],
        "vulnerabilities": ["Important weaknesses or assumptions"],
        "mitigations": ["Practical safeguards"],
        "decision_triggers": ["Conditions that should trigger reconsideration"]
        }

        Include at least three relevant scenarios, such as budget pressure,
        increased usage, provider failure, or changing requirements.

        Use only the supplied context and reasonable explicitly labelled
        assumptions. Do not invent probabilities, measured benchmarks,
        actual costs, or facts. Do not claim to have run real simulations.
        Keep each field concise and actionable.
        """,
    },
}


def run_agent(name: str, task: str) -> str:
    config = AGENTS[name]

    agent = studio.create_agent(
        name=f"TeamMind {name}",
        provider="gpt-4o",
        role=config["role"],
        goal=config["goal"],
        instructions=config["instructions"],
        temperature=0.2,
    )

    response = agent.run(task)
    return str(response.response)


def run_decision_workflow(
    title: str,
    problem: str,
    options: list[str],
    memories: list[dict],
) -> dict:
    # Keep retrieved memory results explicit and readable in every agent prompt.
    # Qdrant results commonly contain document, score, and metadata fields.
    normalized_memories = []
    for item in memories or []:
        if not isinstance(item, dict):
            normalized_memories.append({"document": str(item)})
            continue

        document = (
            item.get("document")
            or item.get("text")
            or item.get("content")
            or item.get("page_content")
        )
        normalized = dict(item)
        if document is not None:
            normalized["document"] = str(document)
        normalized_memories.append(normalized)

    context = {
        "title": title,
        "problem": problem,
        "options": options,
        "relevant_past_memories": normalized_memories,
        "memory_usage_instructions": (
            "Treat relevant retrieved memory text as evidence of previously recorded facts. "
            "Explicitly report relevant facts and their recorded values. Do not call a fact "
            "unknown if it appears in these memories. Its current validity may be unconfirmed. "
            "If a fact is absent, label only that fact unknown; never guess."
        ),
    }

    research = run_agent(
        "Researcher",
        json.dumps(context, ensure_ascii=False),
    )

    analysis = run_agent(
        "Analyst",
        json.dumps({
            "decision": context,
            "research": research,
        }, ensure_ascii=False),
    )

    dissent = run_agent(
        "Dissent Engine",
        json.dumps({
            "decision": context,
            "research": research,
            "analysis": analysis,
        }, ensure_ascii=False),
    )

    verification = run_agent(
        "Verifier",
        json.dumps({
            "decision": context,
            "research": research,
            "analysis": analysis,
            "dissent": dissent,
        }, ensure_ascii=False),
    )
    stress_test = run_agent(
        "Stress Tester",
        json.dumps({
            "decision": context,
            "research": research,
            "analysis": analysis,
            "dissent": dissent,
            "verification": verification,
        }, ensure_ascii=False),
    )

    report = run_agent(
        "Synthesizer",
        json.dumps({
            "decision": context,
            "research": research,
            "analysis": analysis,
            "dissent": dissent,
            "verification": verification,
            "stress_test": stress_test,
        }, ensure_ascii=False),
    )

    return {
        "research": research,
        "analysis": analysis,
        "dissent": dissent,
        "verification": verification,
        "stress_test": stress_test,
        "report": report,
    }

def extract_decision_from_transcript(transcript: str) -> dict:
    """Convert a voice transcript into a structured decision draft."""

    extraction = run_agent(
        "Researcher",
        json.dumps(
            {
                "task": (
                    "Extract a decision draft from this transcript. "
                    "Return valid JSON only, with keys title, problem, "
                    "options. Title must be concise. Problem should "
                    "summarize the actual decision and its context. "
                    "Options must be a list of alternatives explicitly "
                    "mentioned or clearly supported by the transcript. "
                    "Do not invent missing details. If options are unclear, "
                    "return an empty list."
                ),
                "transcript": transcript,
            },
            ensure_ascii=False,
        ),
    )

    cleaned = extraction.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        raise ValueError(
            "Could not extract a valid decision from the transcript."
        )

    if not isinstance(result, dict):
        raise ValueError("The extracted decision must be a JSON object.")

    title = result.get("title")
    problem = result.get("problem")
    options = result.get("options", [])

    if not isinstance(title, str) or not title.strip():
        raise ValueError("The extracted decision has no valid title.")

    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("The extracted decision has no valid problem.")

    if not isinstance(options, list):
        options = []

    return {
        "title": title.strip(),
        "problem": problem.strip(),
        "options": [
            option.strip()
            for option in options
            if isinstance(option, str) and option.strip()
        ],
    }
