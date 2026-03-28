"""Resource example — gRPC MCP client that lists and reads resources.

Run the server first:
    uv run example/resources/server.py

Then run this client:
    uv run example/resources/client.py
"""

import asyncio

from mcp.client.session import ClientSession
from mcp.types import TextResourceContents

from grpcmcp import GRPCClientDispatcher


async def main() -> None:
    dispatcher = GRPCClientDispatcher("localhost", 50051)
    async with ClientSession(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        dispatcher=dispatcher,
    ) as session:
        # List static resources
        resources_result = await session.list_resources()
        print(f"Resources ({len(resources_result.resources)}):")
        for r in resources_result.resources:
            print(f"  - {r.uri}  [{r.name}]")

        # List resource templates
        templates_result = await session.list_resource_templates()
        print(f"\nResource templates ({len(templates_result.resource_templates)}):")
        for t in templates_result.resource_templates:
            print(f"  - {t.uri_template}  [{t.name}]  {t.description}")

        # Read the index resource
        print("\nReading notes://list ...")
        index = await session.read_resource("notes://list")  # type: ignore[arg-type]
        for content in index.contents:
            if isinstance(content, TextResourceContents):
                print(content.text)

        # Read individual notes via the template
        for note_id in ("welcome", "ideas"):
            uri = f"notes://{note_id}"
            print(f"\nReading {uri} ...")
            result = await session.read_resource(uri)  # type: ignore[arg-type]
            for content in result.contents:
                if isinstance(content, TextResourceContents):
                    print(content.text)


if __name__ == "__main__":
    asyncio.run(main())
