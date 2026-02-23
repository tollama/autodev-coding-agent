import httpx
from typing import Any, Dict, List

class LLMClient:
    """Minimal OpenAI-compatible Chat Completions client."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_sec: int = 240):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout_sec

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, headers=headers, json=payload)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                print(f"HTTPStatusError: {e}")
                print(f"Response body: {r.text}")
                raise
            data = r.json()
        return data["choices"][0]["message"]["content"]
