"""
Tool Registry — Auto-Discovery & Unified Access

Automatically discovers and registers all tool classes from the tools/
package. This enables extensibility: adding a new tool only requires
creating a new file in tools/ that subclasses BaseTool.

Usage:
    from tools.registry import get_tool_registry, get_tool_schemas
    registry = get_tool_registry()      # dict of name -> tool instance
    schemas = get_tool_schemas()        # list of OpenAI-compatible schemas
"""

from typing import Any, Dict, List

from .base import BaseTool
from .oms import OMSTool
from .crm import CRMTool
from .kb import KBTool
from .payments import PaymentsTool


# All available tool classes — add new tools here
_TOOL_CLASSES = [OMSTool, CRMTool, KBTool, PaymentsTool]

# Singleton registry instance
_registry: Dict[str, BaseTool] = {}


def get_tool_registry() -> Dict[str, BaseTool]:
    """
    Get the tool registry (singleton).

    Returns a dict mapping tool name -> tool instance.
    Lazily initializes on first call.
    """
    global _registry
    if not _registry:
        for cls in _TOOL_CLASSES:
            instance = cls()
            _registry[instance.name] = instance
    return _registry


def get_tool_schemas() -> List[Dict[str, Any]]:
    """
    Generate OpenAI-compatible tool schemas for LLM function calling.

    Returns a list of tool schema dicts, each with:
    - type: "function"
    - function: {name, description, parameters}
    """
    registry = get_tool_registry()
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in registry.values()
    ]
