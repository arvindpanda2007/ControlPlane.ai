from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI

from .client import ControlPlane, Run
from .cost import calculate_cost
from .injection import InjectionViolation, check_input
from .safety import SafetyViolation, check_output


def _serialize_context(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


class OpenAIClient:
    """
    OpenAI integration for the Application -> Run architecture.

    Developer usage:

        response = openai_client.chat(
            model="gpt-4.1-mini",
            messages=messages,
            run=run,
        )

    Developers never provide application IDs, run IDs, trace IDs,
    span IDs, or parent trace IDs.

    OpenAI usage is captured from response.usage and stored as first-class
    ControlPlane trace fields:
      - input_tokens
      - output_tokens
      - estimated_cost_usd
    """

    def __init__(
        self,
        controlplane: ControlPlane,
        api_key: str | None = None,
    ):
        self.controlplane = controlplane
        self.client = OpenAI(api_key=api_key)

    def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        context: Any = None,
        run: Run | None = None,
        trace: Run | None = None,
    ):
        """
        Execute an OpenAI chat completion and automatically record the
        child LLM trace under the current application run.

        `run` is the preferred argument.

        `trace` is retained as a compatibility alias for older application
        code, but it must still be a Run object returned by app.run().
        """

        if run is None:
            run = trace

        if run is None:
            raise ValueError(
                "OpenAIClient.chat requires the current application run. "
                "Pass run=run from 'with app.run(...) as run:'."
            )

        if not isinstance(run, Run):
            raise TypeError(
                "run must be a ControlPlane Run returned by app.run()."
            )

        start_time = time.perf_counter()
        started_at = datetime.now(timezone.utc)

        # Only untrusted user messages should be inspected by the
        # prompt-injection detector. System/developer instructions and
        # assistant history are trusted control-plane inputs; scanning them
        # can create false positives (e.g. a system prompt discussing
        # instruction overrides).
        input_text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "user"
            and message.get("content") is not None
        )

        trace_context = _serialize_context(context)

        # Internal SDK state. The developer never supplies this ID.
        parent_trace_id = run._trace_id

        if not parent_trace_id:
            raise RuntimeError(
                "The OpenAI call must happen inside an active application run."
            )

        # ---------------------------------------------------------
        # 1. INPUT / PROMPT INJECTION CHECK
        # ---------------------------------------------------------

        try:
            check_input(input_text)

        except InjectionViolation as error:
            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            ended_at = datetime.now(timezone.utc)

            self._record_llm_trace(
                run=run,
                model=model,
                input_text=input_text,
                output_text=None,
                input_tokens=None,
                output_tokens=None,
                latency_ms=latency_ms,
                estimated_cost_usd=None,
                context=trace_context,
                status="blocked",
                safety_flag=True,
                safety_type=",".join(error.matches),
                safety_action="block",
                parent_trace_id=parent_trace_id,
                started_at=started_at,
                ended_at=ended_at,
            )

            raise

        # ---------------------------------------------------------
        # 2. CALL OPENAI
        # ---------------------------------------------------------

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
            )

            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            ended_at = datetime.now(timezone.utc)

            # -----------------------------------------------------
            # 3. EXTRACT OUTPUT
            # -----------------------------------------------------

            output_text = (
                response.choices[0].message.content or ""
            )

            # -----------------------------------------------------
            # 4. EXTRACT REAL OPENAI TOKEN USAGE
            # -----------------------------------------------------

            input_tokens = None
            output_tokens = None

            if response.usage is not None:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens

            # -----------------------------------------------------
            # 5. CALCULATE COST
            # -----------------------------------------------------

            estimated_cost_usd = calculate_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            # -----------------------------------------------------
            # 6. OUTPUT SAFETY CHECK
            # -----------------------------------------------------

            try:
                check_output(output_text)

            except SafetyViolation as error:
                self._record_llm_trace(
                    run=run,
                    model=model,
                    input_text=input_text,
                    output_text=output_text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    estimated_cost_usd=estimated_cost_usd,
                    context=trace_context,
                    status="blocked",
                    safety_flag=True,
                    safety_type=",".join(error.violations),
                    safety_action="block",
                    parent_trace_id=parent_trace_id,
                    started_at=started_at,
                    ended_at=ended_at,
                )

                raise

            # -----------------------------------------------------
            # 7. SUCCESSFUL LLM TRACE
            # -----------------------------------------------------

            self._record_llm_trace(
                run=run,
                model=model,
                input_text=input_text,
                output_text=output_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                estimated_cost_usd=estimated_cost_usd,
                context=trace_context,
                status="success",
                safety_flag=False,
                safety_type=None,
                safety_action=None,
                parent_trace_id=parent_trace_id,
                started_at=started_at,
                ended_at=ended_at,
            )

            return response

        except SafetyViolation:
            raise

        except Exception as error:
            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            ended_at = datetime.now(timezone.utc)

            self._record_llm_trace(
                run=run,
                model=model,
                input_text=input_text,
                output_text=None,
                input_tokens=None,
                output_tokens=None,
                latency_ms=latency_ms,
                estimated_cost_usd=None,
                context=trace_context,
                status="error",
                safety_flag=False,
                safety_type=None,
                safety_action=None,
                parent_trace_id=parent_trace_id,
                started_at=started_at,
                ended_at=ended_at,
                error=error,
            )

            raise

    # =========================================================
    # INTERNAL CONTROLPLANE LLM TRACE RECORDING
    # =========================================================

    def _record_llm_trace(
        self,
        *,
        run: Run,
        model: str,
        input_text: str,
        output_text: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int | None,
        estimated_cost_usd: float | None,
        context: str | None,
        status: str,
        safety_flag: bool,
        safety_type: str | None,
        safety_action: str | None,
        parent_trace_id: str,
        started_at: datetime,
        ended_at: datetime,
        error: Exception | None = None,
    ):
        """
        Persist one OpenAI request as a child trace of the current
        application workflow trace.

        This is internal SDK plumbing. The application developer never
        supplies or creates the trace ID.
        """

        payload: dict[str, Any] = {
            "provider": "openai",
            "model": model,
            "input": input_text,
            "output": output_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "estimated_cost_usd": estimated_cost_usd,
            "context": context,
            "status": status,
            "safety_flag": safety_flag,
            "safety_type": safety_type,
            "safety_action": safety_action,
            "parent_trace_id": parent_trace_id,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
        }

        if error is not None:
            payload["output"] = None

        # Use the SDK's internal child-trace helper.
        # The server creates the actual trace ID.
        self.controlplane._create_trace(
            run_id=run._run_id,
            **payload,
        )


__all__ = ["OpenAIClient"]