import httpx
from concurrent.futures import ThreadPoolExecutor


class ControlPlane:
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8000",
    ):
        self.api_url = api_url.rstrip("/")
        self._executor = ThreadPoolExecutor(max_workers=4)

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
        safety_flag: bool = False,
        safety_type: str | None = None,
        safety_action: str | None = None,
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
            "safety_flag": safety_flag,
            "safety_type": safety_type,
            "safety_action": safety_action,
        }

        self._executor.submit(self._send_trace, payload)

    def _send_trace(self, payload: dict):
        try:
            response = httpx.post(
                f"{self.api_url}/traces",
                json=payload,
                timeout=5.0,
            )

            response.raise_for_status()

        except Exception as error:
            print(f"ControlPlane trace failed: {error}")