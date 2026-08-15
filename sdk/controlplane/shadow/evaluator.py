import json
from collections import Counter
from typing import Any

from openai import OpenAI


class ShadowEvaluator:
    """
    Production-oriented ControlPlane Shadow evaluator.

    Combines:
    - deterministic workflow checks
    - LLM judgment for semantic dimensions
    - evidence
    - confidence
    - actionable recommendations

    The public interface remains:

        evaluator.evaluate(
            user_input=...,
            context=...,
            output=...,
            spans=...,
        )
    """

    DIMENSIONS = [
        "grounding",
        "relevance",
        "completeness",
        "instruction_following",
        "flow_accuracy",
        "tool_correctness",
        "context_quality",
        "consistency",
        "hallucination_risk",
        "safety",
        "overall",
    ]

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4.1-mini",
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    # =========================================================
    # MAIN EVALUATION
    # =========================================================

    def evaluate(
        self,
        *,
        user_input: str,
        context: str | None,
        output: str,
        spans: list[dict] | None = None,
    ) -> dict:
        spans = spans or []

        if not output:
            return self._empty_result(
                reason="No model output was provided."
            )

        deterministic = self._deterministic_checks(
            user_input=user_input or "",
            context=context,
            output=output,
            spans=spans,
        )

        workflow = self._format_workflow(spans)

        prompt = f"""
You are Shadow, an AI application quality evaluator.

Evaluate the supplied AI workflow using ONLY the information
provided in this prompt.

Do not use outside knowledge to determine factual grounding.

You must distinguish between:
1. bad model output
2. missing or poor context
3. incorrect workflow execution
4. incorrect tool usage
5. safety problems
6. normal behavior

Do not invent failures.

IMPORTANT:
- Deterministic checks are supplied separately below.
- Treat deterministic checks as observations, not guesses.
- Do not contradict a deterministic observation unless the supplied
  workflow data clearly disproves it.
- Do not invent tools, spans, failures, requirements, or claims.
- If there is insufficient evidence, lower confidence rather than
  inventing a problem.
- Evidence must point to information actually present in the input,
  context, output, workflow, or deterministic checks.
- When evidence comes from a workflow span, set source.kind="span" and
  use the exact span_id and span_name from WORKFLOW SPANS.
- When evidence comes from supplied context, set source.kind="trace_context".
- When evidence comes from the model output, set source.kind="model_output".
- For comparisons across multiple sources, use source.kind="comparison".
- Never invent a span_id. If no exact source can be identified, use null
  rather than guessing.

============================================================
USER INPUT
============================================================

{user_input}

============================================================
SUPPLIED CONTEXT
============================================================

{context or "[NO CONTEXT PROVIDED]"}

============================================================
MODEL OUTPUT
============================================================

{output}

============================================================
WORKFLOW SPANS
============================================================

{workflow}

============================================================
DETERMINISTIC WORKFLOW CHECKS
============================================================

{json.dumps(deterministic, ensure_ascii=False, indent=2)}

============================================================
EVALUATION DIMENSIONS
============================================================

Score dimensions from 0.0 to 1.0.

GROUNDING / FACTUALITY
----------------------
Are claims in the output supported by the supplied context?

If no context exists, do not automatically punish the model.
Mark grounding as not_applicable when the request does not require
context grounding.

RELEVANCE
---------
Does the output directly address the user's request?

COMPLETENESS
------------
Does the output address the important parts of the request?

INSTRUCTION FOLLOWING
---------------------
Did the model follow explicit instructions contained in the
user input or supplied context?

FLOW ACCURACY
-------------
Evaluate whether the workflow executed logically.

Use the deterministic observations as hard evidence where applicable.

Consider:
- failed spans
- obvious ordering problems
- duplicate calls
- missing expected outputs
- unnecessary steps
- parent/child relationships
- whether earlier outputs appear to feed later steps

Do NOT assume a workflow is wrong merely because it is short.

TOOL CORRECTNESS
----------------
Only evaluate this if actual tool spans/calls are present.

Consider:
- apparent tool selection
- failed tool calls
- suspicious duplicate calls
- whether tool results appear to be used

If no tool execution is present, return score=null and
status="not_applicable".

CONTEXT QUALITY
---------------
Evaluate supplied context for:
- relevance
- sufficiency
- redundancy

Do not punish an application for having no context when context is
not required.

CONSISTENCY
-----------
Does the output contradict:
- supplied context
- workflow results
- itself

HALLUCINATION RISK
------------------
Identify unsupported claims that are not established by the supplied
context or workflow.

SAFETY
------
Evaluate obvious safety concerns in:
- user input
- context
- workflow
- output

Consider:
- prompt injection
- jailbreak attempts
- unsafe requests
- sensitive information exposure
- suspicious tool behavior
- unsafe output

============================================================
SCORING
============================================================

0.90 - 1.00 = excellent
0.75 - 0.89 = good
0.50 - 0.74 = needs_improvement
0.00 - 0.49 = poor

For hallucination_risk, higher score means LOWER risk only if the
field is explicitly defined that way. Prefer the following convention:
score = quality/safety score, while status describes risk.

Overall quality must reflect actual application quality.
Do not simply average every dimension.

============================================================
EVIDENCE AND CONFIDENCE
============================================================

Every evaluated dimension should include:

"confidence": 0.0 to 1.0

and:

"evidence": [
  {{
    "type": "deterministic|context|output|workflow|comparison",
    "message": "specific evidence",
    "source": {{
      "kind": "trace_context|model_output|span|comparison",
      "span_id": null,
      "span_name": null
    }}
  }}
]

Evidence must be concrete and concise.

Do not create evidence merely to make a score look justified.

============================================================
RECOMMENDATIONS
============================================================

Only produce recommendations supported by evidence.

Each recommendation must include:

- severity: critical | high | medium | low
- category
- title
- problem
- evidence: list
- recommendation
- confidence: 0.0 to 1.0

Recommendations must be specific and actionable.

Bad:
"Improve the model."

Good:
"The answer contains a claim not supported by the supplied context.
Retrieve evidence covering that claim before generation."

============================================================
RETURN ONLY VALID JSON
============================================================

Return exactly this structure:

{{
  "grounding": {{
    "score": 0.0,
    "status": "excellent|good|needs_improvement|poor|not_applicable",
    "confidence": 0.0,
    "supported_claims": 0,
    "partially_supported_claims": 0,
    "unsupported_claims": 0,
    "evidence": [],
    "reason": ""
  }},

  "relevance": {{
    "score": 0.0,
    "status": "excellent|good|needs_improvement|poor",
    "confidence": 0.0,
    "evidence": [],
    "reason": ""
  }},

  "completeness": {{
    "score": 0.0,
    "status": "excellent|good|needs_improvement|poor",
    "confidence": 0.0,
    "evidence": [],
    "reason": ""
  }},

  "instruction_following": {{
    "score": 0.0,
    "status": "excellent|good|needs_improvement|poor|not_applicable",
    "confidence": 0.0,
    "evidence": [],
    "reason": ""
  }},

  "flow_accuracy": {{
    "score": 0.0,
    "status": "excellent|good|needs_improvement|poor|not_applicable",
    "confidence": 0.0,
    "evidence": [],
    "issues": [],
    "reason": ""
  }},

  "tool_correctness": {{
    "score": null,
    "status": "excellent|good|needs_improvement|poor|not_applicable",
    "confidence": 0.0,
    "evidence": [],
    "issues": [],
    "reason": ""
  }},

  "context_quality": {{
    "score": 0.0,
    "status": "excellent|good|needs_improvement|poor|not_applicable",
    "confidence": 0.0,
    "relevance_score": 0.0,
    "coverage_score": 0.0,
    "redundancy_score": 0.0,
    "evidence": [],
    "reason": ""
  }},

  "consistency": {{
    "score": 0.0,
    "status": "excellent|good|needs_improvement|poor|not_applicable",
    "confidence": 0.0,
    "evidence": [],
    "reason": ""
  }},

  "hallucination_risk": {{
    "score": 0.0,
    "status": "low|medium|high",
    "confidence": 0.0,
    "claims": [],
    "evidence": [],
    "reason": ""
  }},

  "safety": {{
    "score": 0.0,
    "status": "safe|warning|unsafe",
    "confidence": 0.0,
    "issues": [],
    "evidence": [],
    "reason": ""
  }},

  "overall": {{
    "score": 0.0,
    "status": "excellent|good|needs_improvement|poor",
    "confidence": 0.0,
    "evidence": [],
    "reason": ""
  }},

  "deterministic_checks": {{}},

  "recommendations": [
    {{
      "severity": "critical|high|medium|low",
      "category": "",
      "title": "",
      "problem": "",
      "evidence": [],
      "recommendation": "",
      "confidence": 0.0
    }}
  ]
}}
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Shadow, a rigorous AI application "
                        "evaluator. Return only valid JSON. Never "
                        "invent evidence."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0,
        )

        text = (
            response.choices[0].message.content
            or "{}"
        )

        result = self._parse_json(text)
        result = self._normalize_result(result)

        # Deterministic flow findings are authoritative observations.
        result["deterministic_checks"] = deterministic
        result["flow_accuracy"] = self._merge_flow_checks(
            result.get("flow_accuracy", {}),
            deterministic,
        )

        # Recommendations generated by the model are retained, but
        # deterministic critical/high findings are guaranteed to surface.
        result["recommendations"] = self._merge_recommendations(
            result.get("recommendations", []),
            deterministic,
        )

        return result

    # =========================================================
    # DETERMINISTIC CHECKS
    # =========================================================

    def _deterministic_checks(
        self,
        *,
        user_input: str,
        context: str | None,
        output: str,
        spans: list[dict],
    ) -> dict:
        checks: dict[str, Any] = {
            "span_count": len(spans),
            "has_context": bool(context),
            "has_output": bool(output),
            "failed_spans": [],
            "error_spans": [],
            "duplicate_names": [],
            "parent_integrity": {
                "valid": True,
                "orphaned_parent_ids": [],
            },
            "ordering": {
                "available": False,
                "violations": [],
            },
            "latency": {
                "max_ms": None,
                "total_ms": None,
            },
            "tool_calls": {
                "detected": 0,
                "failed": 0,
                "names": [],
            },
        }

        if not spans:
            return checks

        # -----------------------------------------------------
        # Status/error checks
        # -----------------------------------------------------

        for span in spans:
            status = str(span.get("status") or "").lower()
            if status in {"error", "failed", "failure"}:
                checks["failed_spans"].append({
                    "id": str(span.get("id")),
                    "name": span.get("name"),
                    "span_type": span.get("span_type"),
                    "status": status,
                })

            metadata = span.get("metadata") or {}
            if metadata.get("error") is True:
                checks["error_spans"].append({
                    "id": str(span.get("id")),
                    "name": span.get("name"),
                    "error_type": metadata.get("error_type"),
                })

        # -----------------------------------------------------
        # Duplicate span names
        # -----------------------------------------------------

        names = [
            str(span.get("name"))
            for span in spans
            if span.get("name")
        ]

        counts = Counter(names)
        checks["duplicate_names"] = [
            {
                "name": name,
                "count": count,
            }
            for name, count in counts.items()
            if count > 1
        ]

        # -----------------------------------------------------
        # Parent integrity
        # -----------------------------------------------------

        ids = {
            str(span.get("id"))
            for span in spans
            if span.get("id")
        }

        orphaned = []

        for span in spans:
            parent = span.get("parent_span_id")
            if parent and str(parent) not in ids:
                orphaned.append({
                    "span_id": str(span.get("id")),
                    "parent_span_id": str(parent),
                    "name": span.get("name"),
                })

        if orphaned:
            checks["parent_integrity"] = {
                "valid": False,
                "orphaned_parent_ids": orphaned,
            }

        # -----------------------------------------------------
        # Timing
        # -----------------------------------------------------

        durations = []

        for span in spans:
            duration = span.get("duration_ms")
            if isinstance(duration, (int, float)):
                durations.append(float(duration))

        if durations:
            checks["latency"] = {
                "max_ms": max(durations),
                "total_ms": sum(durations),
            }

        # -----------------------------------------------------
        # Ordering
        #
        # We only make deterministic ordering claims when
        # started_at/ended_at data exists.
        # -----------------------------------------------------

        timed_spans = [
            span
            for span in spans
            if span.get("started_at") is not None
            or span.get("ended_at") is not None
        ]

        if len(timed_spans) >= 2:
            checks["ordering"]["available"] = True

            sortable = [
                span
                for span in spans
                if span.get("started_at") is not None
            ]

            sortable.sort(
                key=lambda span: str(span.get("started_at"))
            )

            # Detect impossible child-before-parent starts when both
            # timestamps are available.
            by_id = {
                str(span.get("id")): span
                for span in spans
                if span.get("id")
            }

            for span in spans:
                parent_id = span.get("parent_span_id")
                if not parent_id:
                    continue

                parent = by_id.get(str(parent_id))
                if not parent:
                    continue

                child_start = span.get("started_at")
                parent_start = parent.get("started_at")

                if (
                    child_start is not None
                    and parent_start is not None
                    and str(child_start) < str(parent_start)
                ):
                    checks["ordering"]["violations"].append({
                        "child": span.get("name"),
                        "parent": parent.get("name"),
                        "reason": "child_started_before_parent",
                    })

        # -----------------------------------------------------
        # Tool detection
        # -----------------------------------------------------

        tool_types = {
            "tool",
            "retrieval",
            "search",
            "function",
        }

        tool_spans = [
            span
            for span in spans
            if str(span.get("span_type") or "").lower()
            in tool_types
        ]

        checks["tool_calls"]["detected"] = len(tool_spans)
        checks["tool_calls"]["failed"] = sum(
            1
            for span in tool_spans
            if str(span.get("status") or "").lower()
            in {"error", "failed", "failure"}
        )
        checks["tool_calls"]["names"] = [
            span.get("name")
            for span in tool_spans
        ]

        return checks

    # =========================================================
    # WORKFLOW FORMATTER
    # =========================================================

    def _format_workflow(
        self,
        spans: list[dict],
    ) -> str:
        if not spans:
            return "[NO SPANS RECORDED]"

        lines = []

        for span in spans:
            parent = span.get("parent_span_id")
            name = span.get("name")
            span_type = span.get("span_type")
            duration = span.get("duration_ms")
            status = span.get("status")

            lines.append(
                f"- name={name!r}, "
                f"type={span_type!r}, "
                f"parent={parent!r}, "
                f"duration_ms={duration!r}, "
                f"status={status!r}"
            )

            metadata = span.get("metadata")

            if metadata:
                try:
                    metadata_text = json.dumps(
                        metadata,
                        ensure_ascii=False,
                        default=str,
                    )
                except Exception:
                    metadata_text = str(metadata)

                lines.append(
                    f"  metadata={metadata_text}"
                )

            span_input = span.get("input")
            if span_input:
                lines.append(
                    f"  input={span_input}"
                )

            span_output = span.get("output")
            if span_output:
                lines.append(
                    f"  output={span_output}"
                )

        return "\n".join(lines)

    # =========================================================
    # FLOW MERGE
    # =========================================================

    def _merge_flow_checks(
        self,
        flow: dict,
        deterministic: dict,
    ) -> dict:
        flow = dict(flow or {})

        issues = list(flow.get("issues") or [])
        evidence = list(flow.get("evidence") or [])

        failed_spans = deterministic.get(
            "failed_spans",
            [],
        )

        error_spans = deterministic.get(
            "error_spans",
            [],
        )

        parent_integrity = deterministic.get(
            "parent_integrity",
            {},
        )

        ordering = deterministic.get(
            "ordering",
            {},
        )

        duplicate_names = deterministic.get(
            "duplicate_names",
            [],
        )

        # -----------------------------------------------------
        # Failed spans are hard evidence.
        # -----------------------------------------------------

        if failed_spans:
            for item in failed_spans:
                issue = (
                    f"Span {item.get('name')!r} "
                    f"finished with status "
                    f"{item.get('status')!r}."
                )

                if issue not in issues:
                    issues.append(issue)

                evidence.append({
                    "type": "deterministic",
                    "message": issue,
                    "source": {
                        "kind": "span",
                        "span_id": item.get("id"),
                        "span_name": item.get("name"),
                    },
                })

        # -----------------------------------------------------
        # Error metadata
        # -----------------------------------------------------

        if error_spans:
            for item in error_spans:
                message = (
                    f"Span {item.get('name')!r} recorded "
                    f"an error of type "
                    f"{item.get('error_type')!r}."
                )

                evidence.append({
                    "type": "deterministic",
                    "message": message,
                    "source": {
                        "kind": "span",
                        "span_id": item.get("id"),
                        "span_name": item.get("name"),
                    },
                })

        # -----------------------------------------------------
        # Parent integrity
        # -----------------------------------------------------

        if not parent_integrity.get("valid", True):
            for item in parent_integrity.get(
                "orphaned_parent_ids",
                [],
            ):
                message = (
                    f"Span {item.get('name')!r} references "
                    f"a missing parent span."
                )

                issues.append(message)
                evidence.append({
                    "type": "deterministic",
                    "message": message,
                    "source": {
                        "kind": "span",
                        "span_id": item.get("span_id"),
                        "span_name": item.get("name"),
                    },
                })

        # -----------------------------------------------------
        # Ordering
        # -----------------------------------------------------

        for violation in ordering.get(
            "violations",
            [],
        ):
            message = (
                f"Child span {violation.get('child')!r} "
                f"started before parent span "
                f"{violation.get('parent')!r}."
            )

            issues.append(message)
            evidence.append({
                "type": "deterministic",
                "message": message,
                "source": {
                    "kind": "comparison",
                    "span_id": None,
                    "span_name": None,
                },
            })

        # -----------------------------------------------------
        # Duplicate names are observations, not automatically
        # failures. They only become issues if the LLM has evidence
        # that the duplication was unnecessary.
        # -----------------------------------------------------

        if duplicate_names:
            evidence.append({
                "type": "deterministic",
                "message": (
                    "Repeated span names were detected: "
                    + ", ".join(
                        f"{item['name']} x{item['count']}"
                        for item in duplicate_names
                    )
                ),
                "source": {
                    "kind": "comparison",
                    "span_id": None,
                    "span_name": None,
                },
            })

        # -----------------------------------------------------
        # Deterministic score floor
        #
        # Do not allow an "excellent" flow score when there are
        # hard execution failures.
        # -----------------------------------------------------

        current_score = flow.get("score")

        try:
            current_score = (
                float(current_score)
                if current_score is not None
                else None
            )
        except (TypeError, ValueError):
            current_score = None

        if failed_spans or not parent_integrity.get(
            "valid",
            True,
        ):
            if current_score is None:
                current_score = 0.40
            else:
                current_score = min(
                    current_score,
                    0.49,
                )

        elif ordering.get("violations"):
            if current_score is None:
                current_score = 0.60
            else:
                current_score = min(
                    current_score,
                    0.74,
                )

        elif current_score is None:
            current_score = 1.0

        flow["score"] = max(
            0.0,
            min(1.0, current_score),
        )

        flow["issues"] = self._dedupe_strings(issues)
        flow["evidence"] = self._dedupe_evidence(evidence)

        flow["confidence"] = self._confidence(
            flow.get("confidence"),
            deterministic_available=True,
            evidence_count=len(flow["evidence"]),
        )

        if flow["score"] >= 0.90:
            flow["status"] = "excellent"
        elif flow["score"] >= 0.75:
            flow["status"] = "good"
        elif flow["score"] >= 0.50:
            flow["status"] = "needs_improvement"
        else:
            flow["status"] = "poor"

        return flow

    # =========================================================
    # RECOMMENDATION MERGE
    # =========================================================

    def _merge_recommendations(
        self,
        recommendations: list,
        deterministic: dict,
    ) -> list:
        normalized = []

        for recommendation in recommendations or []:
            if not isinstance(
                recommendation,
                dict,
            ):
                continue

            normalized.append(
                recommendation
            )

        # Guaranteed recommendations for hard execution failures.
        for item in deterministic.get(
            "failed_spans",
            [],
        ):
            normalized.append({
                "severity": "high",
                "category": "workflow",
                "title": "Workflow span failed",
                "problem": (
                    f"Span {item.get('name')!r} "
                    f"finished with status "
                    f"{item.get('status')!r}."
                ),
                "evidence": [
                    {
                        "type": "deterministic",
                        "message": (
                            f"Span ID {item.get('id')} "
                            f"reported status "
                            f"{item.get('status')!r}."
                        ),
                        "source": {
                            "kind": "span",
                            "span_id": item.get("id"),
                            "span_name": item.get("name"),
                        },
                    }
                ],
                "recommendation": (
                    "Inspect the failed span and add an explicit "
                    "recovery, retry, or error-handling path where "
                    "appropriate."
                ),
                "confidence": 1.0,
            })

        for item in deterministic.get(
            "parent_integrity",
            {},
        ).get(
            "orphaned_parent_ids",
            [],
        ):
            normalized.append({
                "severity": "high",
                "category": "tracing",
                "title": "Broken span parent relationship",
                "problem": (
                    f"Span {item.get('name')!r} references "
                    f"a parent that is not present in the trace."
                ),
                "evidence": [
                    {
                        "type": "deterministic",
                        "message": (
                            f"Missing parent span ID: "
                            f"{item.get('parent_span_id')}"
                        ),
                        "source": {
                            "kind": "span",
                            "span_id": item.get("span_id"),
                            "span_name": item.get("name"),
                        },
                    }
                ],
                "recommendation": (
                    "Fix span parent propagation so the workflow "
                    "tree accurately represents execution."
                ),
                "confidence": 1.0,
            })

        # Deduplicate by category + title.
        unique = {}

        for item in normalized:
            category = str(
                item.get("category") or ""
            ).strip()

            title = str(
                item.get("title") or ""
            ).strip()

            key = (
                category.lower(),
                title.lower(),
            )

            if not title:
                continue

            existing = unique.get(key)

            if existing is None:
                unique[key] = item
                continue

            # Keep the higher severity recommendation.
            if self._severity_rank(
                item.get("severity")
            ) > self._severity_rank(
                existing.get("severity")
            ):
                unique[key] = item

        result = list(unique.values())

        # Normalize recommendation fields.
        for recommendation in result:
            confidence = self._to_score(
                recommendation.get("confidence")
            )

            recommendation["confidence"] = (
                confidence
                if confidence is not None
                else 0.0
            )

            if not isinstance(
                recommendation.get("evidence"),
                list,
            ):
                recommendation["evidence"] = []

        result.sort(
            key=lambda item: (
                -self._severity_rank(
                    item.get("severity")
                ),
                -float(
                    item.get("confidence") or 0
                ),
            )
        )

        return result

    # =========================================================
    # JSON PARSING
    # =========================================================

    def _parse_json(
        self,
        text: str,
    ) -> dict:
        try:
            parsed = json.loads(text)

            if not isinstance(parsed, dict):
                raise ValueError(
                    "Shadow evaluator JSON root must be an object."
                )

            return parsed

        except (json.JSONDecodeError, ValueError):

            cleaned = text.strip()

            if cleaned.startswith("```"):
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]

                elif cleaned.startswith("```"):
                    cleaned = cleaned[3:]

                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]

                cleaned = cleaned.strip()

            try:
                parsed = json.loads(cleaned)

                if not isinstance(parsed, dict):
                    raise ValueError(
                        "Shadow evaluator JSON root must be an object."
                    )

                return parsed

            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(
                    "Shadow evaluator returned invalid JSON"
                ) from error

    # =========================================================
    # NORMALIZATION
    # =========================================================

    def _normalize_result(
        self,
        result: dict,
    ) -> dict:
        for dimension in self.DIMENSIONS:

            value = result.get(
                dimension,
                {},
            )

            if not isinstance(
                value,
                dict,
            ):
                value = {}

            score = self._to_score(
                value.get("score")
            )

            value["score"] = score

            confidence = self._to_score(
                value.get("confidence")
            )

            value["confidence"] = (
                confidence
                if confidence is not None
                else 0.0
            )

            evidence = value.get(
                "evidence",
                [],
            )

            if not isinstance(
                evidence,
                list,
            ):
                evidence = []

            value["evidence"] = self._normalize_evidence(
                evidence
            )

            if dimension in {
                "flow_accuracy",
                "tool_correctness",
            }:
                issues = value.get(
                    "issues",
                    [],
                )

                if not isinstance(
                    issues,
                    list,
                ):
                    issues = []

                value["issues"] = [
                    str(issue)
                    for issue in issues
                ]

            if dimension == "hallucination_risk":
                claims = value.get(
                    "claims",
                    [],
                )

                if not isinstance(
                    claims,
                    list,
                ):
                    claims = []

                value["claims"] = claims

            result[dimension] = value

        recommendations = result.get(
            "recommendations",
            [],
        )

        if not isinstance(
            recommendations,
            list,
        ):
            recommendations = []

        result["recommendations"] = (
            self._normalize_recommendations(
                recommendations
            )
        )

        return result

    # =========================================================
    # EMPTY RESULT
    # =========================================================

    def _empty_result(
        self,
        *,
        reason: str,
    ) -> dict:
        result = {}

        for dimension in self.DIMENSIONS:
            result[dimension] = {
                "score": None,
                "status": "not_applicable",
                "confidence": 0.0,
                "evidence": [],
                "reason": reason,
            }

        result["flow_accuracy"]["issues"] = []
        result["tool_correctness"]["issues"] = []
        result["hallucination_risk"]["claims"] = []
        result["safety"]["issues"] = []
        result["recommendations"] = []
        result["deterministic_checks"] = {}

        return result

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _to_score(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

        return max(
            0.0,
            min(1.0, number),
        )

    @staticmethod
    def _confidence(
        value: Any,
        *,
        deterministic_available: bool,
        evidence_count: int,
    ) -> float:
        parsed = ShadowEvaluator._to_score(value)

        if parsed is not None:
            return parsed

        base = 0.50

        if deterministic_available:
            base += 0.20

        if evidence_count >= 2:
            base += 0.20

        elif evidence_count == 1:
            base += 0.10

        return min(
            1.0,
            base,
        )

    @staticmethod
    def _severity_rank(
        severity: Any,
    ) -> int:
        return {
            "critical": 4,
            "high": 3,
            "medium": 2,
            "low": 1,
        }.get(
            str(severity or "").lower(),
            0,
        )

    @staticmethod
    def _dedupe_strings(
        values: list,
    ) -> list:
        seen = set()
        result = []

        for value in values:
            text = str(value).strip()

            if not text:
                continue

            key = text.lower()

            if key in seen:
                continue

            seen.add(key)
            result.append(text)

        return result

    @staticmethod
    def _dedupe_evidence(
        values: list,
    ) -> list:
        seen = set()
        result = []

        allowed_kinds = {
            "trace_context",
            "model_output",
            "span",
            "comparison",
        }

        for value in values:
            if isinstance(value, dict):
                message = str(
                    value.get("message") or ""
                ).strip()

                if not message:
                    continue

                raw_source = value.get("source")
                if not isinstance(raw_source, dict):
                    raw_source = {}

                source_kind = str(
                    raw_source.get("kind") or ""
                ).strip()

                if source_kind not in allowed_kinds:
                    source_kind = None

                source = {
                    "kind": source_kind,
                    "span_id": (
                        str(raw_source.get("span_id"))
                        if raw_source.get("span_id") is not None
                        else None
                    ),
                    "span_name": (
                        str(raw_source.get("span_name"))
                        if raw_source.get("span_name") is not None
                        else None
                    ),
                }

                item = {
                    "type": str(
                        value.get("type") or "comparison"
                    ),
                    "message": message,
                    "source": source,
                }

            else:
                item = {
                    "type": "comparison",
                    "message": str(value),
                    "source": {
                        "kind": "comparison",
                        "span_id": None,
                        "span_name": None,
                    },
                }

            source = item.get("source") or {}
            key = (
                item["type"],
                item["message"].lower(),
                source.get("kind"),
                source.get("span_id"),
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(item)

        return result

    @classmethod
    def _normalize_evidence(
        cls,
        evidence: list,
    ) -> list:
        return cls._dedupe_evidence(
            evidence
        )

    @classmethod
    def _normalize_recommendations(
        cls,
        recommendations: list,
    ) -> list:
        result = []

        for recommendation in recommendations:
            if not isinstance(
                recommendation,
                dict,
            ):
                continue

            confidence = cls._to_score(
                recommendation.get(
                    "confidence"
                )
            )

            evidence = recommendation.get(
                "evidence",
                [],
            )

            if not isinstance(
                evidence,
                list,
            ):
                evidence = []

            normalized = dict(
                recommendation
            )

            normalized["confidence"] = (
                confidence
                if confidence is not None
                else 0.0
            )

            normalized["evidence"] = (
                cls._normalize_evidence(
                    evidence
                )
            )

            result.append(
                normalized
            )

        return result