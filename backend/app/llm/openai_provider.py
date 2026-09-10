from __future__ import annotations

import json
from typing import Any, Dict

from openai import AsyncOpenAI

from app.llm.base import LLM


def _extract_text(resp: Any) -> str:
    """
    Works across SDK variants:
    - prefer resp.output_text
    - else walk resp.output[*].content[*].text
    """
    if getattr(resp, "output_text", None):
        return resp.output_text

    out = getattr(resp, "output", None)
    if isinstance(out, list):
        for item in out:
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for c in content:
                    text = getattr(c, "text", None)
                    if isinstance(text, str) and text.strip():
                        return text
                    if isinstance(c, dict) and isinstance(c.get("text"), str) and c["text"].strip():
                        return c["text"]

    # last resort
    try:
        return json.dumps(resp.model_dump())
    except Exception:
        return ""


class OpenAILLM(LLM):
    def __init__(self, api_key: str, model_main: str, model_cheap: str):
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your .env file "
                "(get one at https://platform.openai.com/api-keys)."
            )

        # Async client: the sync client blocks the event loop, which stalls
        # every other request while a completion is in flight.
        self.client = AsyncOpenAI(api_key=api_key, timeout=90.0, max_retries=2)
        self.model_main = model_main
        self.model_cheap = model_cheap

    async def generate_text(self, system: str, user: str, temperature: float = 0.2) -> str:
        resp = await self.client.responses.create(
            model=self.model_main,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return _extract_text(resp).strip()

    async def generate_json(
        self,
        system: str,
        user: str,
        schema_name: str,
        schema: Dict[str, Any],
        strict: bool = True,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """
        Structured Outputs (JSON Schema) in the Responses API uses:
          text={ "format": { "type": "json_schema", ... } }
        NOT response_format=...
        """
        resp = await self.client.responses.create(
            model=self.model_main,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": strict,
                    "schema": schema,
                }
            },
        )

        txt = _extract_text(resp).strip()
        if not txt:
            raise RuntimeError("Empty structured output from model")

        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            # Helpful debug if the model returned something unexpected
            raise RuntimeError(f"Model did not return valid JSON. Raw output: {txt[:4000]}")
