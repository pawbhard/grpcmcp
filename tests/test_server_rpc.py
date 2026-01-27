import asyncio
import unittest

import grpc
from mcp.server.fastmcp import Context, FastMCP

from grpcmcp.proto import mcp_pb2, mcp_pb2_grpc
from grpcmcp.server import MCPServicer


class TestServerRPC(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create a FastMCP Server instance
        self.mcp_server = FastMCP("TestServer")
        
        # Register tools
        @self.mcp_server.tool(name="add")
        def add(a: int, b: int) -> int:
            """Add two numbers"""
            return a + b

        @self.mcp_server.tool(name="echo")
        def echo(message: str) -> str:
            """Echo back a message"""
            return "Hello " + message

        @self.mcp_server.tool(name="download_file")
        async def download_file(filename: str, size_mb: float, ctx: Context) -> str:
            """Simulate downloading a file with progress updates."""
            total_bytes = int(size_mb * 1024 * 1024)
            chunk_size = 64 * 1024
            downloaded = 0
            
            while downloaded < total_bytes:
                await asyncio.sleep(0.01) # Faster for tests
                
                downloaded += chunk_size
                if downloaded > total_bytes:
                    downloaded = total_bytes
                
                progress = downloaded / total_bytes
                
                await ctx.report_progress(
                    progress, 1.0, f"Downloaded {downloaded} bytes"
                )
                
            return f"Successfully downloaded {filename}"

        # Create the servicer
        self.servicer = MCPServicer(self.mcp_server)
        
        self.server = grpc.aio.server()
        mcp_pb2_grpc.add_McpServicer_to_server(self.servicer, self.server)
        port = self.server.add_insecure_port('localhost:0')
        await self.server.start()
        
        self.channel = grpc.aio.insecure_channel(f'localhost:{port}')
        self.stub = mcp_pb2_grpc.McpStub(self.channel)

    async def asyncTearDown(self):
        await self.channel.close()
        await self.server.stop(None)

    async def test_list_tools(self):
        request = mcp_pb2.ListToolsRequest()
        response = await self.stub.ListTools(request)
        
        self.assertEqual(len(response.tools), 3)
        tool_names = [t.name for t in response.tools]
        self.assertIn("add", tool_names)
        self.assertIn("echo", tool_names)
        self.assertIn("download_file", tool_names)
        
        # Verify schema for add
        add_tool = next(t for t in response.tools if t.name == "add")
        self.assertEqual(add_tool.description, "Add two numbers")
        self.assertIn("properties", add_tool.input_schema)
        self.assertIn("a", add_tool.input_schema["properties"])
        self.assertIn("b", add_tool.input_schema["properties"])
        
        # FastMCP might not set output_schema by default for simple types
        # so we skip strict output_schema checks unless we define Pydantic models
        # Verify outputSchema
        self.assertTrue(
            add_tool.HasField("output_schema"),
            "output_schema should be present"
        )
        self.assertIn("properties", add_tool.output_schema)
        self.assertIn("result", add_tool.output_schema["properties"])

    async def test_call_tool(self):
        from google.protobuf.struct_pb2 import Struct
        args = Struct()
        args.update({"message": "World"})
        
        request = mcp_pb2.CallToolRequest(
            request=mcp_pb2.CallToolRequest.Request(
                name="echo",
                arguments=args
            )
        )
        
        # CallTool returns a stream
        responses = []
        async for response in self.stub.CallTool(request):
            responses.append(response)
            
        self.assertTrue(len(responses) > 0)
        # Check content
        found_content = False
        for response in responses:
            if response.content:
                for content in response.content:
                    if content.text.text == "Hello World":
                        found_content = True
        
        self.assertTrue(found_content, "Did not find expected response 'Hello World'")

    async def test_call_tool_structured(self):
        from google.protobuf.struct_pb2 import Struct
        args = Struct()
        args.update({"a": 10, "b": 20})
        
        request = mcp_pb2.CallToolRequest(
            request=mcp_pb2.CallToolRequest.Request(
                name="add",
                arguments=args
            )
        )
        
        responses = []
        async for response in self.stub.CallTool(request):
            responses.append(response)
            
        self.assertTrue(len(responses) > 0)
        
        # Check structured_content
        found_result = False
        for response in responses:
            if response.HasField("structured_content"):
                # FastMCP returns {'result': 30} for add(10, 20)
                if response.structured_content["result"] == 30:
                    found_result = True
        
        self.assertTrue(found_result, "Did not find expected structured result 30")

    async def test_call_tool_with_progress(self):
        from google.protobuf.struct_pb2 import Struct
        args = Struct()
        # Small size to make test fast, but enough for a few chunks
        # 0.2 MB = 204.8 KB. Chunk 64KB. ~4 chunks.
        args.update({"filename": "test.txt", "size_mb": 0.2})
        
        request = mcp_pb2.CallToolRequest(
            common=mcp_pb2.RequestFields(
                progress=mcp_pb2.ProgressNotification(progress_token="test-token")
            ),
            request=mcp_pb2.CallToolRequest.Request(
                name="download_file",
                arguments=args
            )
        )
        
        responses = []
        progress_updates = []
        final_result = None
        
        async for response in self.stub.CallTool(request):
            responses.append(response)
            if response.common.HasField('progress'):
                progress_updates.append(response.common.progress)
            
            if response.content:
                for content in response.content:
                    final_result = content.text.text
        
        self.assertTrue(len(progress_updates) > 0, "No progress updates received")
        # Final progress check might be aprox 1.0 depending on loop
        self.assertGreaterEqual(progress_updates[-1].progress, 0.9)
        self.assertEqual(final_result, "Successfully downloaded test.txt")

if __name__ == '__main__':
    unittest.main()
