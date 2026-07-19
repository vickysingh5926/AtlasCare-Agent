"""
Base Tool — Abstract interface for all AtlasCare tools.

All tools (OMS, CRM, KB, Payments) inherit from BaseTool and implement
the `execute()` method. The unified interface enables:
- Automatic tool schema generation for LLM function calling
- Dynamic tool registry / auto-discovery
- Consistent execution and error handling patterns
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """
    Abstract base class for all AtlasCare tools.

    Subclasses must define:
        name: Unique tool identifier used in LLM function calling
        description: Human-readable description for the LLM to decide when to call
        parameters: JSON Schema dict describing accepted parameters

    Subclasses must implement:
        execute(params): Async method that performs the tool action
    """

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the tool with the given parameters.

        Args:
            params: Dictionary of parameters matching the tool's JSON schema.

        Returns:
            Dictionary with at least:
            - status (str): "success" or "error"
            - message (str): Human-readable result description
            - data (dict, optional): Structured result data
        """
        raise NotImplementedError
