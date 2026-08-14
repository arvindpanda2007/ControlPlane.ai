import time

from openai import OpenAI

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
        session_id: str | None = None,
    ):
        start_time = time.perf_counter()

        # ---------------------------------------------------------
        # 1. Extract input
        # ---------------------------------------------------------

        input_text = "\n".join(
            message["content"]
            for message in messages
            if message.get("content")
        )

        # ---------------------------------------------------------
        # 2. INLINE PROMPT-INJECTION CHECK
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
                session_id=session_id,
                status="blocked",
                safety_flag=True,
                safety_type=",".join(error.matches),
                safety_action="block",
            )

            # IMPORTANT:
            # OpenAI has NOT been called.
            raise

        # ---------------------------------------------------------
        # 3. CALL OPENAI
        # ---------------------------------------------------------

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
            )

            # -----------------------------------------------------
            # 4. Measure model latency
            # -----------------------------------------------------

            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            # -----------------------------------------------------
            # 5. Extract output
            # -----------------------------------------------------

            output_text = response.choices[0].message.content or ""

            # -----------------------------------------------------
            # 6. Extract token usage
            # -----------------------------------------------------

            input_tokens = None
            output_tokens = None

            if response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens

            # -----------------------------------------------------
            # 7. INLINE OUTPUT SAFETY CHECK
            # -----------------------------------------------------

            try:
                check_output(output_text)

            except SafetyViolation as error:
                self.controlplane.trace(
                    provider="openai",
                    model=model,
                    input=input_text,
                    output=output_text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    session_id=session_id,
                    status="blocked",
                    safety_flag=True,
                    safety_type=",".join(error.violations),
                    safety_action="block",
                )

                # Do NOT return unsafe output
                raise

            # -----------------------------------------------------
            # 8. SAFE RESPONSE → RECORD TRACE
            # -----------------------------------------------------

            self.controlplane.trace(
                provider="openai",
                model=model,
                input=input_text,
                output=output_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                session_id=session_id,
                status="success",
                safety_flag=False,
                safety_type=None,
                safety_action=None,
            )

            # -----------------------------------------------------
            # 9. Return response
            # -----------------------------------------------------

            return response

        except SafetyViolation:
            raise

        except Exception:
            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            self.controlplane.trace(
                provider="openai",
                model=model,
                input=input_text,
                latency_ms=latency_ms,
                session_id=session_id,
                status="error",
                safety_flag=False,
                safety_type=None,
                safety_action=None,
            )

            raise