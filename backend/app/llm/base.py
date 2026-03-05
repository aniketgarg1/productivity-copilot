from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLM(ABC):
    @abstractmethod
    async def generate_text(self, system: str, user: str, temperature: float = 0.2) -> str:
        ...

    @abstractmethod
    async def generate_json(
        self,
        system: str,
        user: str,
        schema_name: str,
        schema: Dict[str, Any],
        strict: bool = True,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        ...