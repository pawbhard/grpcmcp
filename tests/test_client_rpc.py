"""Unit tests for GRPCClientDispatcher against a fake in-process gRPC servicer."""
# pylint: disable=unnecessary-dunder-call
import unittest

import grpc
from google.protobuf.struct_pb2 import Struct  # pylint: disable=no-name-in-module
from mcp.client.session import ClientSession
from mcp.types import TextContent
from mcp_transport_proto import (
    mcp_messages_pb2,  # pylint: disable=no-member
    mcp_pb2_grpc,
)

from grpcmcp.client import GRPCClientDispatcher


class FakeMcpServicer(mcp_pb2_grpc.McpServicer):
    """Minimal in-process servicer that returns hard-coded responses."""

    async def ListTools(self, _request, _context):  # pylint: disable=invalid-overridden-method
        input_schema = Struct()
        input_schema.update({
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        })
        return mcp_messages_pb2.ListToolsResponse(tools=[
            mcp_messages_pb2.Tool(
                name="fake_tool",
                description="A fake tool",
                input_schema=input_schema,
            )
        ])

    async def CallTool(self, request, _context):  # pylint: disable=invalid-overridden-method
        tool_name = request.request.name
        return mcp_messages_pb2.CallToolResponse(
            content=[
                mcp_messages_pb2.CallToolResponse.Content(
                    text=mcp_messages_pb2.TextContent(text=f"called {tool_name}")
                )
            ],
            is_error=False,
        )


class TestClientRPC(unittest.IsolatedAsyncioTestCase):
    """Test GRPCClientDispatcher against a fake gRPC servicer."""

    async def asyncSetUp(self):
        self.grpc_server = grpc.aio.server()
        mcp_pb2_grpc.add_McpServicer_to_server(FakeMcpServicer(), self.grpc_server)
        port = self.grpc_server.add_insecure_port("localhost:0")
        await self.grpc_server.start()

        self.dispatcher = GRPCClientDispatcher("localhost", port)
        self._session = ClientSession(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            dispatcher=self.dispatcher,
        )
        await self._session.__aenter__()

    async def asyncTearDown(self):
        await self._session.__aexit__(None, None, None)
        await self.grpc_server.stop(None)

    async def test_list_tools(self):
        result = await self._session.list_tools()
        self.assertEqual(len(result.tools), 1)
        self.assertEqual(result.tools[0].name, "fake_tool")
        self.assertEqual(result.tools[0].description, "A fake tool")

    async def test_call_tool(self):
        result = await self._session.call_tool("fake_tool", {"x": 42})
        self.assertFalse(result.is_error)
        self.assertEqual(len(result.content), 1)
        self.assertIsInstance(result.content[0], TextContent)
        self.assertEqual(result.content[0].text, "called fake_tool")


if __name__ == "__main__":
    unittest.main()
