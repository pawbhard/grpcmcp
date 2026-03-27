import asyncio

import grpc
import mcp.types as types
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct
from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import request_ctx as server_request_ctx

from .adapter import GRPCSessionAdapter
from .context import GRPCRequestContext
from .proto import mcp_messages_pb2 as mcp_pb2, mcp_pb2_grpc


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
            
            # Queue not used but required by GRPCSessionAdapter signature
            adapter = GRPCSessionAdapter(asyncio.Queue())
            request_context = GRPCRequestContext.from_grpc(request, adapter)
            token = server_request_ctx.set(request_context)
            
            try:
                result = await self.fastmcp.call_tool(tool_name, arguments)
                
                content_blocks = []
                metadata_dict = {}
                if isinstance(result, tuple) and len(result) > 0:
                    content_blocks = result[0]
                    if len(result) > 1 and isinstance(result[1], dict):
                        metadata_dict = result[1]
                elif isinstance(result, list):
                    content_blocks = result
                else:
                    content_blocks = [result] if result else []
                
                proto_contents = []
                for content in content_blocks:
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

                return mcp_pb2.CallToolResponse(
                    content=proto_contents,
                    structured_content=structured_content,
                    is_error=False
                )
            finally:
                server_request_ctx.reset(token)
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return mcp_pb2.CallToolResponse(
                content=[mcp_pb2.CallToolResponse.Content(
                    text=mcp_pb2.TextContent(text=str(e))
                )],
                is_error=True
            )
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

