import time

from openai import OpenAI

from .cost import calculate_cost
from .client import ControlPlane
from .injection import InjectionViolation, check_input
from .safety import SafetyViolation, check_output


class OpenAIClient:
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
        context: str | None = None,
        session_id: str | None = None,
        trace=None,
    ):
        start_time = time.perf_counter()

        input_text = "\n".join(
            message["content"]
            for message in messages
            if message.get("content")
        )

        # ---------------------------------------------------------
        # WORKFLOW TRACE ID
        # ---------------------------------------------------------

        parent_trace_id = trace.id if trace else None

        # ---------------------------------------------------------
        # 1. INPUT / PROMPT INJECTION CHECK
        # ---------------------------------------------------------

        try:
            check_input(input_text)

        except InjectionViolation as error:
            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            self.controlplane.trace(
                provider="openai",
                model=model,
                input=input_text,
                latency_ms=latency_ms,
                estimated_cost_usd=None,
                context=context,
                session_id=session_id,
                status="blocked",
                safety_flag=True,
                safety_type=",".join(error.matches),
                safety_action="block",
                parent_trace_id=parent_trace_id,
            )

            raise

        # ---------------------------------------------------------
        # 2. CREATE LLM SPAN
        # ---------------------------------------------------------

        llm_span = None

        if trace:
            llm_span = trace.span(
                "openai",
                span_type="llm",

                # Record the exact input sent to this step.
                input=input_text,
            )

            llm_span.__enter__()

        try:
            # -----------------------------------------------------
            # 3. CALL OPENAI
            # -----------------------------------------------------

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
            )

            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            # -----------------------------------------------------
            # 4. EXTRACT OUTPUT
            # -----------------------------------------------------

            output_text = (
                response.choices[0].message.content or ""
            )

            # Record the exact output produced by this step.
            if llm_span:
                llm_span.output = output_text

            # -----------------------------------------------------
            # 5. EXTRACT TOKEN USAGE
            # -----------------------------------------------------

            input_tokens = None
            output_tokens = None

            if response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens

            # -----------------------------------------------------
            # 6. CALCULATE COST
            # -----------------------------------------------------

            estimated_cost_usd = calculate_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            # -----------------------------------------------------
            # 7. UPDATE LLM SPAN METADATA
            # -----------------------------------------------------

            if llm_span:
                llm_span.metadata.update(
                    {
                        "model": model,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "estimated_cost_usd": estimated_cost_usd,
                    }
                )

            # -----------------------------------------------------
            # 8. OUTPUT SAFETY CHECK
            # -----------------------------------------------------

            try:
                check_output(output_text)

            except SafetyViolation as error:

                if llm_span:
                    llm_span.metadata.update(
                        {
                            "safety_flag": True,
                            "safety_type": ",".join(
                                error.violations
                            ),
                            "safety_action": "block",
                        }
                    )

                    llm_span.__exit__(
                        SafetyViolation,
                        error,
                        error.__traceback__,
                    )

                    llm_span = None

                self.controlplane.trace(
                    provider="openai",
                    model=model,
                    input=input_text,
                    output=output_text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    estimated_cost_usd=estimated_cost_usd,
                    context=context,
                    session_id=session_id,
                    status="blocked",
                    safety_flag=True,
                    safety_type=",".join(error.violations),
                    safety_action="block",
                    parent_trace_id=parent_trace_id,
                )

                raise

            # -----------------------------------------------------
            # 9. SAFE RESPONSE
            # -----------------------------------------------------

            if llm_span:
                llm_span.metadata.update(
                    {
                        "safety_flag": False,
                        "safety_type": None,
                        "safety_action": None,
                    }
                )

                llm_span.__exit__(
                    None,
                    None,
                    None,
                )

                llm_span = None

            self.controlplane.trace(
                provider="openai",
                model=model,
                input=input_text,
                output=output_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                estimated_cost_usd=estimated_cost_usd,
                context=context,
                session_id=session_id,
                status="success",
                safety_flag=False,
                safety_type=None,
                safety_action=None,
                parent_trace_id=parent_trace_id,
            )

            return response

        except SafetyViolation:
            raise

        except Exception as error:

            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            if llm_span:
                llm_span.metadata.update(
                    {
                        "error": True,
                        "error_type": type(error).__name__,
                    }
                )

                llm_span.__exit__(
                    type(error),
                    error,
                    error.__traceback__,
                )

                llm_span = None

            self.controlplane.trace(
                provider="openai",
                model=model,
                input=input_text,
                latency_ms=latency_ms,
                estimated_cost_usd=None,
                context=context,
                session_id=session_id,
                status="error",
                safety_flag=False,
                safety_type=None,
                safety_action=None,
                parent_trace_id=parent_trace_id,
            )

            raise