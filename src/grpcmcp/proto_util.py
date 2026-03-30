"""Conversion helpers between mcp.types and mcp_transport_proto message types.

Server direction (mcp → proto): used by MCPServicer to build responses.
Client direction (proto → mcp): used by GRPCClient to parse responses.
"""

from typing import Any

import mcp.types as types
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct  # pylint: disable=no-name-in-module
from mcp_transport_proto import mcp_messages_pb2 as mcp_pb2  # pylint: disable=no-member

# ---------------------------------------------------------------------------
# Server direction: mcp.types → proto
# ---------------------------------------------------------------------------


def tool_to_proto(tool: types.Tool) -> Any:
    input_schema = Struct()
    if tool.inputSchema:
        ParseDict(tool.inputSchema, input_schema)

    kwargs: dict[str, Any] = {
        "name": tool.name,
        "title": tool.title or "",
        "description": tool.description or "",
        "input_schema": input_schema,
    }
    if tool.outputSchema:
        output_schema = Struct()
        ParseDict(tool.outputSchema, output_schema)
        kwargs["output_schema"] = output_schema

    return mcp_pb2.Tool(**kwargs)


def call_content_to_proto(content: Any) -> Any:
    """Convert a single mcp content block to a CallToolResponse.Content proto.

    Returns None for unsupported content types.
    """
    if isinstance(content, types.TextContent):
        return mcp_pb2.CallToolResponse.Content(
            text=mcp_pb2.TextContent(text=content.text)
        )
    if isinstance(content, types.ImageContent):
        return mcp_pb2.CallToolResponse.Content(
            image=mcp_pb2.ImageContent(data=content.data, mime_type=content.mimeType)
        )
    # Fallback for duck-typed text objects
    if getattr(content, "type", None) == "text":
        return mcp_pb2.CallToolResponse.Content(
            text=mcp_pb2.TextContent(text=getattr(content, "text", ""))
        )
    return None


# ---------------------------------------------------------------------------
# Client direction: proto → mcp.types
# ---------------------------------------------------------------------------


def proto_to_tool(proto: Any) -> types.Tool:
    input_schema = MessageToDict(proto.input_schema)
    output_schema: dict[str, Any] | None = None
    if proto.HasField("output_schema"):
        output_schema = MessageToDict(proto.output_schema)

    return types.Tool(
        name=proto.name,
        title=proto.title or None,
        description=proto.description or None,
        inputSchema=input_schema,
        outputSchema=output_schema,
    )


def proto_content_to_mcp(
    proto: Any,
) -> types.TextContent | types.ImageContent:
    # ListFields() returns only explicitly-set fields; use it instead of
    # WhichOneof because Content fields are not declared inside a proto oneof.
    set_fields = proto.ListFields()
    if not set_fields:
        raise ValueError("CallToolResponse.Content has no field set")
    field_name = set_fields[0][0].name
    if field_name == "text":
        return types.TextContent(type="text", text=proto.text.text)
    if field_name == "image":
        return types.ImageContent(
            type="image", data=proto.image.data, mimeType=proto.image.mime_type
        )
    if field_name == "audio":
        raise NotImplementedError("AudioContent is not supported")
    if field_name == "resource_link":
        raise NotImplementedError("ResourceLink is not supported")
    if field_name == "embedded_resource":
        raise NotImplementedError("EmbeddedResource is not yet supported")
    raise ValueError(f"Unknown content field: {field_name!r}")


def proto_to_call_tool_result(proto: Any) -> types.CallToolResult:
    content = [proto_content_to_mcp(c) for c in proto.content]
    structured: dict[str, Any] | None = None
    if proto.HasField("structured_content"):
        structured = MessageToDict(proto.structured_content)
    return types.CallToolResult(
        content=content,
        structuredContent=structured,
        isError=proto.is_error,
    )
