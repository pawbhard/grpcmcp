import unittest

import grpc
from mcp.server.fastmcp import FastMCP
from mcp_transport_proto import mcp_pb2_grpc

from grpcmcp.client import GRPCClient
from grpcmcp.server import MCPServicer


class TestClientRPC(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mcp_server = FastMCP("TestServer")

        @self.mcp_server.tool(name="add")
        def add(a: int, b: int) -> int:
            """Add two numbers"""
            return a + b

        @self.mcp_server.tool(name="echo")
        def echo(message: str) -> str:
            """Echo back a message"""
            return "Hello " + message

        self.server = grpc.aio.server()
        mcp_pb2_grpc.add_McpServicer_to_server(
            MCPServicer(self.mcp_server), self.server
        )
        port = self.server.add_insecure_port("localhost:0")
        await self.server.start()

        self.client = await GRPCClient("localhost", port).__aenter__()

    async def asyncTearDown(self):
        await self.client.__aexit__(None, None, None)
        await self.server.stop(None)

    async def test_list_tools_returns_all_tools(self):
        result = await self.client.list_tools()

        self.assertEqual(len(result.tools), 2)
        names = {t.name for t in result.tools}
        self.assertIn("add", names)
        self.assertIn("echo", names)

    async def test_list_tools_tool_metadata(self):
        result = await self.client.list_tools()

        add = next(t for t in result.tools if t.name == "add")
        self.assertEqual(add.description, "Add two numbers")
        self.assertIn("properties", add.inputSchema)
        self.assertIn("a", add.inputSchema["properties"])
        self.assertIn("b", add.inputSchema["properties"])

    async def test_list_tools_output_schema(self):
        result = await self.client.list_tools()

        add = next(t for t in result.tools if t.name == "add")
        self.assertIsNotNone(add.outputSchema)
        self.assertIn("properties", add.outputSchema)
        self.assertIn("result", add.outputSchema["properties"])

    async def test_call_tool_text_content(self):
        result = await self.client.call_tool("echo", {"message": "World"})

        self.assertFalse(result.isError)
        texts = [c.text for c in result.content if c.type == "text"]
        self.assertIn("Hello World", texts)

    async def test_call_tool_structured_content(self):
        result = await self.client.call_tool("add", {"a": 10, "b": 20})

        self.assertFalse(result.isError)
        self.assertIsNotNone(result.structuredContent)
        self.assertEqual(result.structuredContent["result"], 30)

    async def test_call_tool_unknown_returns_error(self):
        result = await self.client.call_tool("nonexistent_tool", {})

        self.assertTrue(result.isError)
        self.assertTrue(len(result.content) > 0)

    async def test_call_tool_timeout_raises(self):
        with self.assertRaises(grpc.aio.AioRpcError) as cm:
            await self.client.call_tool("echo", {"message": "hi"}, timeout=0.000001)
        self.assertEqual(cm.exception.code(), grpc.StatusCode.DEADLINE_EXCEEDED)


if __name__ == "__main__":
    unittest.main()
