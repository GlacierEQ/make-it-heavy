from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        raise NotImplementedError

    def to_openrouter_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
