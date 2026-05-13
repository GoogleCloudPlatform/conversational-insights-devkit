# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
"""
Meta-Prompting Optimization Logic for QAI Optimization Framework.

This module implements the "Gemini 3 Reasoning Architecture" pattern to optimize
scorecard items based on disagreement evidence between AI and human raters.
"""

import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError
from google import genai
from google.genai import types
from cxidk.workflow.insight_refinements.utils import handle_api_quota, qai_logger

# Configure logging
logger = logging.getLogger(__name__)

# --- Pydantic Models ---


class DisagreementCase(BaseModel):
    """Model for validating input evidence."""

    turn: Optional[str] = Field(
        default=None, description="The transcript text where the issue occurred"
    )
    human: str = Field(description="Human rater's score")
    ai: str = Field(description="AI's score")
    reason: Optional[str] = Field(
        default=None, description="Explanation for the disagreement"
    )


class OptimizedScorecard(BaseModel):
    """Schema for the optimized scorecard output."""

    refined_question: str = Field(description="The polished question")
    refined_instructions: str = Field(description="Step-by-step logic for the AI")
    refined_answers: List[str] = Field(description="Mutually exclusive answer choices")
    reasoning_log: str = Field(description="Internal monologue explaining changes")
    edge_cases: List[str] = Field(description="Specific scenarios handled")


class VerificationResult(BaseModel):
    """Schema for individual verification checks."""

    score: str
    reason: str


# --- Prompt Templates ---

SYSTEM_TEMPLATE = """
<role>
You are the **Quality Architect**. Your goal is to optimize "Scorecard Items" for automated AI evaluation.
You must ensure high **Inter-Rater Reliability (Cohen's Kappa)** between the AI and Human Auditors.
</role>

<constraints>
1. **Domain Standards:** Follow best practices for QA scoring (objectivity, clarity).
2. **Logic Gaps:** Identify why original instructions fail (Ambiguity, Label Leakage, N/A handling).
3. **Mutually Exclusive:** Answer choices must not overlap.
4. **Reasoning:** You MUST use <thinking> tags to plan your optimization before generating the final JSON.
</constraints>

<output_format>
You will output a strict JSON object matching the requested schema.
</output_format>
"""

USER_PROMPT_TEMPLATE = """
<current_rule>
    <question>{question}</question>
    <instructions>{instructions}</instructions>
    <answers>{answers}</answers>
</current_rule>

{examples_section}

{evidence_section}

<task>
Analyze the evidence provided. The AI failed to match the Human rater in these cases.
Refine the question and instructions to prevent these specific failures.
Ensure the logic handles the edge cases shown in the transcripts.
</task>
"""

VERIFICATION_PROMPT_TEMPLATE = """
<role>
You are a **Literal-Minded AI Evaluator**.
Your only job is to apply the following instructions strictly and objectively.
Do not use outside knowledge. Do not be "smart."
Only follow the steps provided in the <instructions> block.
</role>

<instructions>
{new_instructions}
</instructions>

<transcript_turn>
{turn_text}
</transcript_turn>

<task>
Based ONLY on the instructions above, what is the correct answer for this transcript?
Select one from: {allowed_answers}
Provide your answer in the following JSON format:
{{"score": "YOUR_SELECTED_ANSWER", "reason": "BRIEF_LOGIC_FROM_INSTRUCTIONS"}}
</task>
"""


class ScorecardOptimizer:
    """
    Orchestrates the meta-prompting loop to refine scorecard items.
    """

    def __init__(
        self,
        project_id: str,
        location_id: str,
        model_name: str = "gemini-3.1-flash-lite-preview",
    ):
        """
        Initializes the optimizer with Vertex AI client.

        Args:
            project_id (str): GCP Project ID.
            location_id (str): GCP Region.
            model_name (str): Gemini model to use (default: gemini-3.1-flash-lite-preview).
        """
        self.client = genai.Client(
            vertexai=True, project=project_id, location=location_id
        )
        self.model_name = model_name
        self.verification_model = model_name  # Use same model to match location config

    def _format_evidence(self, raw_examples: List[Dict[str, Any]]) -> str:
        """Formats disagreement cases into XML for the prompt."""
        if not raw_examples:
            return ""
        try:
            cases = [DisagreementCase(**ex) for ex in raw_examples]
        except ValidationError as e:
            logger.warning(f"Validation Error in Evidence: {e}")
            return "<error>Invalid Evidence Data</error>"

        evidence_str = "<disagreement_evidence>\n"
        for i, case in enumerate(cases):
            evidence_str += (
                f"  <case_{i + 1}>\n"
                f"    <transcript_turn>{case.turn or 'N/A'}</transcript_turn>\n"
                f"    <human_rating>{case.human}</human_rating>\n"
                f"    <ai_rating>{case.ai}</ai_rating>\n"
                f"    <insight>{case.reason or 'N/A'}</insight>\n"
                f"  </case_{i + 1}>\n"
            )
        evidence_str += "</disagreement_evidence>"
        return evidence_str

    @handle_api_quota()
    def optimize_question(
        self,
        question: str,
        instructions: str,
        answers: List[str],
        disagreement_cases: List[Dict[str, Any]],
        reference_examples: Optional[List[Dict[str, str]]] = None,
    ) -> OptimizedScorecard:
        """
        Generates an optimized version of the scorecard question logic.

        Args:
            question (str): The original question text.
            instructions (str): The original instructions.
            answers (List[str]): List of answer choices.
            disagreement_cases (List[Dict]): A list of scenarios where the AI and Human disagreed.
                                           These are used as "negative constraints" to force the model
                                           to fix its logic.
                                           Format: [{"turn": "...", "human": "Yes", "ai": "No", "reason": "..."}]
            reference_examples (List[Dict]): Optional list of "Gold Standard" examples where the label is known to be correct.
                                           These are used as "positive patterns" to teach the model the desired behavior.
                                           Format: [{"turn": "...", "label": "Yes", "reason": "Matches criteria X"}]

        Returns:
            OptimizedScorecard: The refined rule.
        """
        evidence_str = self._format_evidence(disagreement_cases)
        answers_str = ", ".join(answers)

        # Format optional reference examples
        examples_str = ""
        if reference_examples:
            examples_str = "<reference_examples>\n"
            for ex in reference_examples:
                examples_str += (
                    f"  <example>\n"
                    f"    <turn>{ex.get('turn', 'N/A')}</turn>\n"
                    f"    <label>{ex.get('label', 'N/A')}</label>\n"
                    f"    <reason>{ex.get('reason', 'N/A')}</reason>\n"
                    f"  </example>\n"
                )
            examples_str += "</reference_examples>"

        prompt = USER_PROMPT_TEMPLATE.format(
            question=question,
            instructions=instructions,
            answers=answers_str,
            examples_section=examples_str,
            evidence_section=evidence_str,
        )

        qai_logger.log("Generating optimization...", severity="INFO")

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[
                types.Content(role="system", parts=[types.Part(text=SYSTEM_TEMPLATE)]),
                types.Content(role="user", parts=[types.Part(text=prompt)]),
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,  # Low temp for precision
                response_mime_type="application/json",
                response_schema=OptimizedScorecard,
            ),
        )

        return response.parsed

    @handle_api_quota()
    def verify_optimization(
        self, scorecard: OptimizedScorecard, evidence: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Tests the optimized scorecard against the provided evidence cases.
        Returns a list of failures (where the new rule still disagrees with the Human).
        """
        failures = []
        qai_logger.log(
            f"Verifying against {len(evidence)} examples...", severity="INFO"
        )

        for i, ex in enumerate(evidence):
            try:
                case = DisagreementCase(**ex)
                prompt = VERIFICATION_PROMPT_TEMPLATE.format(
                    new_instructions=scorecard.refined_instructions,
                    turn_text=case.turn or "N/A",
                    allowed_answers=", ".join(scorecard.refined_answers),
                )

                response = self.client.models.generate_content(
                    model=self.verification_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        response_mime_type="application/json",
                        response_schema=VerificationResult,
                    ),
                )
                v_result = response.parsed

                # Check for agreement with HUMAN (Ground Truth)
                if v_result.score.strip().lower() != case.human.strip().lower():
                    failures.append(
                        {
                            "case_id": i + 1,
                            "expected": case.human,
                            "actual": v_result.score,
                            "model_reasoning": v_result.reason,
                        }
                    )
            except Exception as e:
                logger.error(f"Verification failed for case {i}: {e}")
                failures.append({"case_id": i, "error": str(e)})

        return failures
