# pylint: disable=protected-access,unnecessary-dunder-call
import asyncio
import unittest

import anyio
import grpc
from google.protobuf.struct_pb2 import Struct  # pylint: disable=no-name-in-module
from mcp.server.mcpserver.server import MCPServer
from mcp.server.session import ServerSession
from mcp_transport_proto import (
    mcp_messages_pb2,  # pylint: disable=no-member
    mcp_pb2_grpc,
)

from grpcmcp.server import GRPCDispatcher


class TestServerRPC(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mcp_server = MCPServer("TestServer")

        @self.mcp_server.tool(name="add")
        def add(a: int, b: int) -> int:
            """Add two numbers"""
            return a + b

        @self.mcp_server.tool(name="echo")
        def echo(message: str) -> str:
            """Echo back a message"""
            return "Hello " + message

        lowlevel = self.mcp_server._lowlevel_server  # type: ignore[attr-defined]
        self.dispatcher = GRPCDispatcher()
        init_options = lowlevel.create_initialization_options()

        # Enter the session so set_handlers is called and the dispatcher is ready.
        self._session = ServerSession(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            init_options,
            stateless=True,
            dispatcher=self.dispatcher,
        )
        await self._session.__aenter__()

        # Run the message dispatch loop in a background asyncio task.
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

    async def test_list_tools(self):
        request = mcp_messages_pb2.ListToolsRequest()
        response = await self.stub.ListTools(request)

        self.assertEqual(len(response.tools), 2)
        tool_names = [t.name for t in response.tools]
        self.assertIn("add", tool_names)
        self.assertIn("echo", tool_names)

        add_tool = next(t for t in response.tools if t.name == "add")
        self.assertEqual(add_tool.description, "Add two numbers")
        self.assertIn("properties", add_tool.input_schema)
        self.assertIn("a", add_tool.input_schema["properties"])
        self.assertIn("b", add_tool.input_schema["properties"])

        self.assertTrue(
            add_tool.HasField("output_schema"),
            "output_schema should be present",
        )
        self.assertIn("properties", add_tool.output_schema)
        self.assertIn("result", add_tool.output_schema["properties"])

    async def test_call_tool(self):
        args_struct = Struct()
        args_struct.update({"message": "World"})

        request = mcp_messages_pb2.CallToolRequest(
            request=mcp_messages_pb2.CallToolRequest.Request(
                name="echo", arguments=args_struct
            )
        )
        response = await self.stub.CallTool(request)

        found_content = any(
            c.text.text == "Hello World" for c in response.content
        )
        self.assertTrue(found_content, "Did not find expected response 'Hello World'")

    async def test_call_tool_structured(self):
        args = Struct()
        args.update({"a": 10, "b": 20})

        request = mcp_messages_pb2.CallToolRequest(
            request=mcp_messages_pb2.CallToolRequest.Request(name="add", arguments=args)
        )
        response = await self.stub.CallTool(request)

        self.assertTrue(
            response.HasField("structured_content"),
            "structured_content should be present",
        )
        self.assertEqual(response.structured_content["result"], 30)


if __name__ == "__main__":
    unittest.main()
