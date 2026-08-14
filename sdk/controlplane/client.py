import httpx


class ControlPlane:
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8000",
    ):
        self.api_url = api_url.rstrip("/")

    def trace(
        self,
        *,
        provider: str,
        model: str,
        input: str,
        output: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
        session_id: str | None = None,
        status: str = "success",
    ):
        payload = {
            "provider": provider,
            "model": model,
            "input": input,
            "output": output,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "session_id": session_id,
            "status": status,
        }

        response = httpx.post(
            f"{self.api_url}/traces",
            json=payload,
            timeout=5.0,
        )

        response.raise_for_status()

        return response.json()