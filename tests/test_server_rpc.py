# pylint: disable=protected-access,unnecessary-dunder-call
import asyncio
import unittest

import anyio
import grpc
from google.protobuf.struct_pb2 import Struct  # pylint: disable=no-name-in-module
from mcp.server.mcpserver.server import MCPServer
from mcp.server.session import ServerSession
from mcp.types import Completion, PromptReference
from mcp_transport_proto import (
    mcp_messages_pb2,  # pylint: disable=no-member
    mcp_pb2_grpc,
)

from grpcmcp.server import GRPCDispatcher


class TestServerRPC(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mcp_server = MCPServer("TestServer")

        # --- Tools ---
        @self.mcp_server.tool(name="add")
        def add(a: int, b: int) -> int:
            """Add two numbers"""
            return a + b

        @self.mcp_server.tool(name="echo")
        def echo(message: str) -> str:
            """Echo back a message"""
            return "Hello " + message

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
            "test://{item_id}",
            name="item",
            description="An item by ID",
        )
        def item_resource(item_id: str) -> str:
            return f"item: {item_id}"

        # --- Prompts ---
        @self.mcp_server.prompt(name="greet", description="Greet someone")
        def greet_prompt(name: str) -> str:
            return f"Hello, {name}!"

        # --- Completion ---
        @self.mcp_server.completion()
        async def complete(ref, argument, context):  # type: ignore[no-untyped-def]
            if isinstance(ref, PromptReference) and ref.name == "greet":
                if argument.name == "name":
                    return Completion(values=["Alice", "Bob"])
            return Completion(values=[])

        lowlevel = self.mcp_server._lowlevel_server  # type: ignore[attr-defined]
        self.dispatcher = GRPCDispatcher()
        init_options = lowlevel.create_initialization_options()

        self._session = ServerSession(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            init_options,
            stateless=True,
            dispatcher=self.dispatcher,
        )
        await self._session.__aenter__()

        async def _dispatch_loop() -> None:
            async with anyio.create_task_group() as tg:
                async for message in self._session.incoming_messages:
                    tg.start_soon(
                        lowlevel._handle_message,  # type: ignore[attr-defined]
                        message,
                        self._session,
                        {},
                        False,
                    )

        self._dispatch_task = asyncio.create_task(_dispatch_loop())

        self.server = grpc.aio.server()
        mcp_pb2_grpc.add_McpServicer_to_server(self.dispatcher, self.server)
        port = self.server.add_insecure_port("localhost:0")
        await self.server.start()

        self.channel = grpc.aio.insecure_channel(f"localhost:{port}")
        self.stub = mcp_pb2_grpc.McpStub(self.channel)

    async def asyncTearDown(self):
        await self.channel.close()
        await self.server.stop(None)
        self._dispatch_task.cancel()
        try:
            await self._dispatch_task
        except asyncio.CancelledError:
            pass
        await self._session.__aexit__(None, None, None)

    # --- Tools ---

    async def test_list_tools(self):
        response = await self.stub.ListTools(mcp_messages_pb2.ListToolsRequest())

        self.assertEqual(len(response.tools), 2)
        tool_names = [t.name for t in response.tools]
        self.assertIn("add", tool_names)
        self.assertIn("echo", tool_names)

        add_tool = next(t for t in response.tools if t.name == "add")
        self.assertEqual(add_tool.description, "Add two numbers")
        self.assertIn("properties", add_tool.input_schema)
        self.assertIn("a", add_tool.input_schema["properties"])
        self.assertIn("b", add_tool.input_schema["properties"])
        self.assertTrue(add_tool.HasField("output_schema"))
        self.assertIn("result", add_tool.output_schema["properties"])

    async def test_call_tool(self):
        args = Struct()
        args.update({"message": "World"})
        response = await self.stub.CallTool(
            mcp_messages_pb2.CallToolRequest(
                request=mcp_messages_pb2.CallToolRequest.Request(
                    name="echo", arguments=args
                )
            )
        )
        self.assertTrue(any(c.text.text == "Hello World" for c in response.content))

    async def test_call_tool_structured(self):
        args = Struct()
        args.update({"a": 10, "b": 20})
        response = await self.stub.CallTool(
            mcp_messages_pb2.CallToolRequest(
                request=mcp_messages_pb2.CallToolRequest.Request(
                    name="add", arguments=args
                )
            )
        )
        self.assertTrue(response.HasField("structured_content"))
        self.assertEqual(response.structured_content["result"], 30)

    # --- Resources ---

    async def test_list_resources(self):
        response = await self.stub.ListResources(
            mcp_messages_pb2.ListResourcesRequest()
        )
        uris = [r.uri for r in response.resources]
        self.assertIn("test://hello", uris)

        hello = next(r for r in response.resources if r.uri == "test://hello")
        self.assertEqual(hello.name, "hello")
        self.assertEqual(hello.description, "A hello resource")
        self.assertEqual(hello.mime_type, "text/plain")

    async def test_read_resource(self):
        response = await self.stub.ReadResource(
            mcp_messages_pb2.ReadResourceRequest(uri="test://hello")
        )
        self.assertEqual(len(response.resource), 1)
        content = response.resource[0]
        self.assertEqual(content.uri, "test://hello")
        self.assertEqual(content.text, "hello world")

    async def test_list_resource_templates(self):
        response = await self.stub.ListResourceTemplates(
            mcp_messages_pb2.ListResourceTemplatesRequest()
        )
        templates = {t.name: t for t in response.resource_templates}
        self.assertIn("item", templates)
        self.assertEqual(templates["item"].uri_template, "test://{item_id}")

    # --- Prompts ---

    async def test_list_prompts(self):
        response = await self.stub.ListPrompts(mcp_messages_pb2.ListPromptsRequest())
        names = [p.name for p in response.prompts]
        self.assertIn("greet", names)

        greet = next(p for p in response.prompts if p.name == "greet")
        self.assertEqual(greet.description, "Greet someone")
        self.assertTrue(any(a.name == "name" for a in greet.arguments))

    async def test_get_prompt(self):
        request = mcp_messages_pb2.GetPromptRequest(name="greet")
        request.arguments["name"] = "World"
        response = await self.stub.GetPrompt(request)

        self.assertEqual(len(response.messages), 1)
        msg = response.messages[0]
        self.assertEqual(msg.role, mcp_messages_pb2.ROLE_USER)
        self.assertTrue(msg.HasField("text"))
        self.assertEqual(msg.text.text, "Hello, World!")

    # --- Completion ---

    async def test_complete(self):
        response = await self.stub.Complete(
            mcp_messages_pb2.CompletionRequest(
                prompt_reference=mcp_messages_pb2.PromptReference(name="greet"),
                argument=mcp_messages_pb2.CompletionRequest.Argument(
                    name="name", value="Al"
                ),
            )
        )
        self.assertIn("Alice", response.values)

    async def test_complete_no_match(self):
        response = await self.stub.Complete(
            mcp_messages_pb2.CompletionRequest(
                prompt_reference=mcp_messages_pb2.PromptReference(name="greet"),
                argument=mcp_messages_pb2.CompletionRequest.Argument(
                    name="unknown_arg", value=""
                ),
            )
        )
        self.assertEqual(list(response.values), [])


if __name__ == "__main__":
    unittest.main()
