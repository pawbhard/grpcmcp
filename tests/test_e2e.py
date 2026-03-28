"""E2E tests: full stack MCPServer → GRPCDispatcher → gRPC → ClientSession."""

# pylint: disable=protected-access,unnecessary-dunder-call
import asyncio
import unittest

import anyio
import grpc
from mcp.client.session import ClientSession
from mcp.server.mcpserver.server import MCPServer
from mcp.server.session import ServerSession
from mcp.types import Completion, PromptReference, TextContent
from mcp_transport_proto import mcp_pb2_grpc  # pylint: disable=no-member

from grpcmcp.client import GRPCClientDispatcher
from grpcmcp.server import GRPCDispatcher


class TestE2E(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # --- Server side ---
        self.mcp_server = MCPServer("E2EServer")

        @self.mcp_server.tool(name="multiply")
        def multiply(a: int, b: int) -> int:
            """Multiply two numbers"""
            return a * b

        @self.mcp_server.tool(name="slow")
        async def slow(seconds: float) -> str:
            """Sleep for the given number of seconds, then return."""
            await asyncio.sleep(seconds)
            return "done"

        @self.mcp_server.tool(name="boom")
        def boom(x: int) -> str:
            """Always raises an exception."""
            raise ValueError("intentional boom")

        @self.mcp_server.tool(name="bad_output")
        def bad_output(x: int) -> int:
            """Declared to return int but actually returns a string."""
            return "this is not an int"  # type: ignore[return-value]

        @self.mcp_server.tool(name="sum_two")
        def sum_two(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        # --- Resources ---
        @self.mcp_server.resource(
            "test://hello",
            name="hello",
            description="A hello resource",
            mime_type="text/plain",
        )
        def hello_resource() -> str:
            return "hello world"

        @self.mcp_server.resource(
            "test://greet/{name}",
            name="greet_template",
            description="Greet by name",
        )
        def greet_resource(name: str) -> str:
            return f"Hello, {name}!"

        # --- Prompts ---
        @self.mcp_server.prompt(name="greet", description="Greet someone")
        def greet_prompt(name: str) -> str:
            return f"Hello, {name}!"

        # --- Completion ---
        @self.mcp_server.completion()
        async def complete(ref, argument, context):  # type: ignore[no-untyped-def]
            if isinstance(ref, PromptReference) and ref.name == "greet":
                if argument.name == "name":
                    return Completion(values=["Alice", "Bob", "World"])
            return Completion(values=[])

        lowlevel = self.mcp_server._lowlevel_server  # type: ignore[attr-defined]
        self.server_dispatcher = GRPCDispatcher()
        init_options = lowlevel.create_initialization_options()

        self._server_session = ServerSession(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            init_options,
            stateless=True,
            dispatcher=self.server_dispatcher,
        )
        await self._server_session.__aenter__()

        async def _dispatch_loop() -> None:
            async with anyio.create_task_group() as tg:
                async for message in self._server_session.incoming_messages:
                    tg.start_soon(
                        lowlevel._handle_message,  # type: ignore[attr-defined]
                        message,
                        self._server_session,
                        {},
                        False,
                    )

        self._dispatch_task = asyncio.create_task(_dispatch_loop())

        self.grpc_server = grpc.aio.server()
        mcp_pb2_grpc.add_McpServicer_to_server(self.server_dispatcher, self.grpc_server)
        port = self.grpc_server.add_insecure_port("localhost:0")
        await self.grpc_server.start()

        # --- Client side ---
        self.client_dispatcher = GRPCClientDispatcher("localhost", port)
        self._client_session = ClientSession(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            dispatcher=self.client_dispatcher,
        )
        await self._client_session.__aenter__()

    async def asyncTearDown(self):
        await self._client_session.__aexit__(None, None, None)
        await self.grpc_server.stop(None)
        self._dispatch_task.cancel()
        try:
            await self._dispatch_task
        except asyncio.CancelledError:
            pass
        await self._server_session.__aexit__(None, None, None)

    def _text_content(self, result) -> list[str]:
        return [c.text for c in result.content if isinstance(c, TextContent)]

    async def test_list_tools(self):
        result = await self._client_session.list_tools()
        tool_names = [t.name for t in result.tools]
        self.assertIn("multiply", tool_names)

    async def test_call_tool(self):
        result = await self._client_session.call_tool("multiply", {"a": 6, "b": 7})
        self.assertFalse(result.is_error)
        self.assertIsNotNone(result.structured_content)
        self.assertEqual(result.structured_content["result"], 42)

    async def test_slow_tool_cancelled(self):
        """Cancelling a task mid-flight raises CancelledError and cleans up."""
        task = asyncio.create_task(
            self._client_session.call_tool("slow", {"seconds": 10})
        )
        await asyncio.sleep(0.1)  # let the gRPC call get in-flight
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_tool_raises_exception(self):
        """A tool that raises returns is_error=True with the exception message."""
        result = await self._client_session.call_tool("boom", {"x": 1})

        self.assertTrue(result.is_error)
        texts = self._text_content(result)
        self.assertTrue(
            any("intentional boom" in t for t in texts),
            f"Expected 'intentional boom' in content, got: {texts}",
        )

    async def test_tool_not_found(self):
        """Calling a non-existent tool returns is_error=True."""
        result = await self._client_session.call_tool("no_such_tool", {})

        self.assertTrue(result.is_error)
        texts = self._text_content(result)
        self.assertTrue(
            any("no_such_tool" in t for t in texts),
            f"Expected tool name in error content, got: {texts}",
        )

    async def test_input_schema_mismatch(self):
        """Passing the wrong type for an argument returns is_error=True."""
        result = await self._client_session.call_tool(
            "sum_two", {"a": "not_an_int", "b": 2}
        )

        self.assertTrue(result.is_error)
        texts = self._text_content(result)
        self.assertTrue(
            any("validation error" in t.lower() for t in texts),
            f"Expected validation error in content, got: {texts}",
        )

    async def test_output_schema_mismatch(self):
        """A tool returning the wrong type returns is_error=True."""
        result = await self._client_session.call_tool("bad_output", {"x": 1})

        self.assertTrue(result.is_error)
        texts = self._text_content(result)
        self.assertTrue(
            any("validation error" in t.lower() for t in texts),
            f"Expected validation error in content, got: {texts}",
        )

    # --- Resources ---

    async def test_list_resources(self):
        result = await self._client_session.list_resources()
        uris = [r.uri for r in result.resources]
        self.assertIn("test://hello", uris)

    async def test_read_resource(self):
        from mcp.types import TextResourceContents

        result = await self._client_session.read_resource("test://hello")  # type: ignore[arg-type]
        self.assertEqual(len(result.contents), 1)
        self.assertIsInstance(result.contents[0], TextResourceContents)
        self.assertEqual(result.contents[0].text, "hello world")

    async def test_list_resource_templates(self):
        result = await self._client_session.list_resource_templates()
        names = [t.name for t in result.resource_templates]
        self.assertIn("greet_template", names)

    # --- Prompts ---

    async def test_list_prompts(self):
        result = await self._client_session.list_prompts()
        names = [p.name for p in result.prompts]
        self.assertIn("greet", names)
        greet = next(p for p in result.prompts if p.name == "greet")
        self.assertEqual(greet.description, "Greet someone")
        self.assertTrue(any(a.name == "name" for a in (greet.arguments or [])))

    async def test_get_prompt(self):
        result = await self._client_session.get_prompt("greet", {"name": "World"})
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.messages[0].role, "user")
        self.assertIsInstance(result.messages[0].content, TextContent)
        self.assertEqual(result.messages[0].content.text, "Hello, World!")  # type: ignore[union-attr]

    # --- Completion ---

    async def test_complete(self):
        result = await self._client_session.complete(
            ref={"type": "ref/prompt", "name": "greet"},  # type: ignore[arg-type]
            argument={"name": "name", "value": "Al"},  # type: ignore[arg-type]
        )
        self.assertIn("Alice", result.completion.values)


if __name__ == "__main__":
    unittest.main()
