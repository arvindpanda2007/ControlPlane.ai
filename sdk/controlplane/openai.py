import time

from openai import OpenAI

from .client import ControlPlane


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

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
            )

            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            input_text = "\n".join(
                message["content"]
                for message in messages
                if message.get("content")
            )

            output_text = response.choices[0].message.content or ""

            input_tokens = None
            output_tokens = None

            if response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens

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
            )

            return response

        except Exception:
            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            self.controlplane.trace(
                provider="openai",
                model=model,
                input=str(messages),
                latency_ms=latency_ms,
                session_id=session_id,
                status="error",
            )

            raise