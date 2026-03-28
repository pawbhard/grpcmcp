"""Prompt example — gRPC MCP client that lists, gets prompts, and uses completion.

Run the server first:
    uv run example/prompts/server.py

Then run this client:
    uv run example/prompts/client.py
"""

import asyncio

from mcp.client.session import ClientSession
from mcp.types import TextContent

from grpcmcp import GRPCClientDispatcher


async def main() -> None:
    dispatcher = GRPCClientDispatcher("localhost", 50051)
    async with ClientSession(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        dispatcher=dispatcher,
    ) as session:
        # List available prompts
        prompts_result = await session.list_prompts()
        print(f"Prompts ({len(prompts_result.prompts)}):")
        for p in prompts_result.prompts:
            args = ", ".join(a.name for a in (p.arguments or []))
            print(f"  - {p.name}({args}): {p.description}")

        # Get the code_review prompt
        print("\nGetting code_review prompt ...")
        review = await session.get_prompt(
            "code_review",
            {"code": "def add(a, b):\n    return a + b", "language": "python"},
        )
        for msg in review.messages:
            if isinstance(msg.content, TextContent):
                print(f"[{msg.role}] {msg.content.text}")

        # Get the explain prompt
        print("\nGetting explain prompt ...")
        explain = await session.get_prompt(
            "explain",
            {"concept": "gRPC", "audience": "junior developer"},
        )
        for msg in explain.messages:
            if isinstance(msg.content, TextContent):
                print(f"[{msg.role}] {msg.content.text}")

        # Completion — autocomplete the language argument
        print("\nCompletion for language='py' ...")
        completion = await session.complete(
            ref={"type": "ref/prompt", "name": "code_review"},  # type: ignore[arg-type]
            argument={"name": "language", "value": "py"},  # type: ignore[arg-type]
        )
        print(f"Suggestions: {completion.completion.values}")

        print("\nCompletion for language='r' ...")
        completion = await session.complete(
            ref={"type": "ref/prompt", "name": "code_review"},  # type: ignore[arg-type]
            argument={"name": "language", "value": "r"},  # type: ignore[arg-type]
        )
        print(f"Suggestions: {completion.completion.values}")


if __name__ == "__main__":
    asyncio.run(main())
