"""Prompt example — gRPC MCP server exposing prompts with argument completion.

Run this server:
    uv run example/prompts/server.py

Then run the matching client:
    uv run example/prompts/client.py
"""

import asyncio

from mcp.server.mcpserver.server import MCPServer
from mcp.types import Completion, PromptReference

from grpcmcp import serve_grpc

mcp = MCPServer("Prompts Example Server")

LANGUAGES = ["python", "typescript", "go", "rust", "java"]


@mcp.prompt(name="code_review", description="Generate a code review prompt")
def code_review(code: str, language: str = "python") -> str:
    """Ask the model to review a code snippet in a given language."""
    return (
        f"Please review the following {language} code and provide feedback on "
        f"correctness, style, and potential improvements:\n\n```{language}\n{code}\n```"
    )


@mcp.prompt(name="explain", description="Explain a concept simply")
def explain(concept: str, audience: str = "beginner") -> str:
    """Ask the model to explain a concept for a target audience."""
    return f"Explain '{concept}' in simple terms suitable for a {audience}."


@mcp.completion()
async def complete(ref, argument, context):  # type: ignore[no-untyped-def]
    if isinstance(ref, PromptReference) and ref.name == "code_review":
        if argument.name == "language":
            prefix = argument.value.lower()
            matches = [lang for lang in LANGUAGES if lang.startswith(prefix)]
            return Completion(values=matches)
    return Completion(values=[])


if __name__ == "__main__":
    asyncio.run(serve_grpc(mcp, enable_reflection=True))
