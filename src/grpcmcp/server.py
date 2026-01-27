import asyncio

import grpc
import mcp.types as types
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct
from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import request_ctx as server_request_ctx

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
                if tool.inputSchema:
                    ParseDict(tool.inputSchema, input_schema)
                
                output_schema = None
                if tool.outputSchema:
                    output_schema = Struct()
                    ParseDict(tool.outputSchema, output_schema)

                tool_kwargs = {
                    "name": tool.name,
                    "title": tool.title or "",
                    "description": tool.description or "",
                    "input_schema": input_schema,
                }
                if output_schema:
                    tool_kwargs["output_schema"] = output_schema

                proto_tools.append(mcp_pb2.Tool(**tool_kwargs))
            
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
                token = None
                try:
                    # Set up context for FastMCP to find
                    request_context = GRPCRequestContext.from_grpc(
                        request, adapter
                    )
                    # We use the low-level request_ctx which FastMCP seems to respect
                    # (FastMCP.get_context uses self._mcp_server.request_context)
                    token = server_request_ctx.set(request_context)
                    
                    # Execute tool via FastMCP
                    result = await self.fastmcp.call_tool(tool_name, arguments)
                    
                    # Result from FastMCP.call_tool can be (content, meta) tuple
                    # or just content. Based on observation, it returns a tuple
                    # where first element is content list.
                    content_blocks = []
                    metadata_dict = {}
                    if isinstance(result, tuple) and len(result) > 0:
                        content_blocks = result[0]
                        if len(result) > 1 and isinstance(result[1], dict):
                            metadata_dict = result[1]
                    elif isinstance(result, list):
                        content_blocks = result
                    else:
                        # Fallback if it returns distinct type 
                        # (e.g. dict for structured?)
                        # But for now assume it returns content blocks sequence.
                        content_blocks = [result] if result else []
                    
                    # Convert result to proto
                    proto_contents = []
                    for content in content_blocks:
                        # content is likely mcp.types.Content 
                        # (TextContent, ImageContent, etc.)
                        
                        # Use hasattr for flexible typing or isinstance 
                        # if types imported
                        if isinstance(content, types.TextContent):
                            proto_contents.append(mcp_pb2.CallToolResponse.Content(
                                text=mcp_pb2.TextContent(text=content.text)
                            ))
                        elif isinstance(content, types.ImageContent):
                            proto_contents.append(mcp_pb2.CallToolResponse.Content(
                                image=mcp_pb2.ImageContent(
                                    data=content.data,
                                    mime_type=content.mimeType
                                )
                            ))
                        elif isinstance(content, types.EmbeddedResource):
                             pass
                        else:
                            # Fallback using getattr for duck-typing 
                            # if it's a dict or other object
                            ctype = getattr(content, "type", None)
                            if ctype == "text":
                                text = getattr(content, "text", "")
                                proto_contents.append(mcp_pb2.CallToolResponse.Content(
                                    text=mcp_pb2.TextContent(text=text)
                                ))
                    

                    structured_content = None
                    if metadata_dict:
                        try:
                            structured_content = Struct()
                            ParseDict(metadata_dict, structured_content)
                        except Exception:
                            import traceback
                            traceback.print_exc()
                            # Continue without structured content if parsing fails

                    final_response = mcp_pb2.CallToolResponse(
                        content=proto_contents,
                        structured_content=structured_content,
                        is_error=False
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
                    if token:
                        server_request_ctx.reset(token)
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

async def serve_grpc(server: FastMCP, host="0.0.0.0", port=50051):
    grpc_server = grpc.aio.server()
    mcp_pb2_grpc.add_McpServicer_to_server(MCPServicer(server), grpc_server)
    listen_addr = f'[::]:{port}'
    grpc_server.add_insecure_port(listen_addr)
    print(f"Starting gRPC server on {listen_addr}")
    await grpc_server.start()
    await grpc_server.wait_for_termination()

