import asyncio

import grpc
from fastmcp import FastMCP
from fastmcp.server.context import Context
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct

from .adapter import GRPCSessionAdapter
from .context import GRPCRequestContext
from .proto import mcp_pb2, mcp_pb2_grpc


class MCPServicer(mcp_pb2_grpc.McpServicer):
    def __init__(self, fastmcp: FastMCP):
        self.fastmcp = fastmcp

    async def ListTools(self, request, context):
        try:
            tools = await self.fastmcp.list_tools()
            
            from google.protobuf.json_format import ParseDict
            proto_tools = []
            for tool in tools:
                input_schema = Struct()
                if tool.parameters:
                    ParseDict(tool.parameters, input_schema)
                
                output_schema = Struct()
                if tool.output_schema:
                    ParseDict(tool.output_schema, output_schema)
                
                proto_tools.append(mcp_pb2.Tool(
                    name=tool.name,
                    title=tool.title or "",
                    description=tool.description or "",
                    input_schema=input_schema,
                    output_schema=output_schema
                ))
                
            return mcp_pb2.ListToolsResponse(tools=proto_tools)
        except Exception:
            import traceback
            traceback.print_exc()
            raise

    async def CallTool(self, request, context):
        try:
            tool_name = request.request.name
            arguments = MessageToDict(request.request.arguments)
            
            response_queue = asyncio.Queue()
            adapter = GRPCSessionAdapter(response_queue)
            
            # Start tool execution in a task
            async def execute_tool():
                try:
                    async with Context(fastmcp=self.fastmcp, session=adapter):
                        # Injects progress token if provided in metadata
                        # Set up the request context
                        request_context = GRPCRequestContext.from_grpc(
                            request, adapter
                        )
                        from mcp.server.lowlevel.server import request_ctx
                        token = request_ctx.set(request_context)
                        
                        try:
                            result = await self.fastmcp.call_tool(
                                tool_name, arguments
                            )
                        finally:
                            request_ctx.reset(token)
                        
                        # Convert result to proto
                        # result is ToolResult
                        proto_contents = []
                        for content in result.content:
                            if content.type == "text":
                                proto_contents.append(mcp_pb2.CallToolResponse.Content(
                                    text=mcp_pb2.TextContent(text=content.text)
                                ))
                            # Handle other types if needed
                        
                        structured_content = Struct()
                        if result.structured_content:
                            from google.protobuf.json_format import ParseDict
                            ParseDict(result.structured_content, structured_content)
                            
                        final_response = mcp_pb2.CallToolResponse(
                            content=proto_contents,
                            structured_content=structured_content,
                            is_error=False # Handle errors
                        )
                        await response_queue.put(final_response)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    error_response = mcp_pb2.CallToolResponse(
                        content=[mcp_pb2.CallToolResponse.Content(
                            text=mcp_pb2.TextContent(text=str(e))
                        )],
                        is_error=True
                    )
                    await response_queue.put(error_response)
                finally:
                    await response_queue.put(None) # Signal end of stream

            asyncio.create_task(execute_tool())
            
            while True:
                response = await response_queue.get()
                if response is None:
                    break
                yield response
        except Exception:
            import traceback
            traceback.print_exc()
            raise

async def serve_grpc(fastmcp: FastMCP, host="0.0.0.0", port=50051):
    server = grpc.aio.server()
    mcp_pb2_grpc.add_McpServicer_to_server(MCPServicer(fastmcp), server)
    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    print(f"Starting gRPC server on {listen_addr}")
    await server.start()
    await server.wait_for_termination()
