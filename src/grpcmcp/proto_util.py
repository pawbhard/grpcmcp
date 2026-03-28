"""Conversions between MCP Python types and mcp_transport_proto message types.

Two directions:
  mcp_*_to_proto  — MCP type → proto message  (used by server to build responses)
  proto_*_to_dict — proto message → dict       (used by client for ClientSession)
"""

import base64
from typing import Any

from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct  # pylint: disable=no-name-in-module
from mcp import types
from mcp_transport_proto import mcp_messages_pb2  # pylint: disable=no-member

# ---------------------------------------------------------------------------
# MCP types → proto
# ---------------------------------------------------------------------------


def tool_to_proto(tool: types.Tool) -> Any:
    input_schema = Struct()
    if tool.input_schema:
        ParseDict(tool.input_schema, input_schema)

    kwargs: dict[str, Any] = {
        "name": tool.name,
        "title": tool.title or "",
        "description": tool.description or "",
        "input_schema": input_schema,
    }
    if tool.output_schema:
        output_schema = Struct()
        ParseDict(tool.output_schema, output_schema)
        kwargs["output_schema"] = output_schema

    return mcp_messages_pb2.Tool(**kwargs)


def call_content_to_proto(
    content: types.TextContent | types.ImageContent | types.AudioContent,
) -> Any | None:
    if isinstance(content, types.TextContent):
        return mcp_messages_pb2.CallToolResponse.Content(
            text=mcp_messages_pb2.TextContent(text=content.text)
        )
    if isinstance(content, types.ImageContent):
        return mcp_messages_pb2.CallToolResponse.Content(
            image=mcp_messages_pb2.ImageContent(
                data=content.data, mime_type=content.mimeType
            )
        )
    if isinstance(content, types.AudioContent):
        return mcp_messages_pb2.CallToolResponse.Content(
            audio=mcp_messages_pb2.AudioContent(
                data=content.data, mime_type=content.mimeType
            )
        )
    return None


def resource_to_proto(r: types.Resource) -> Any:
    return mcp_messages_pb2.Resource(
        uri=r.uri,
        name=r.name,
        title=r.title or "",
        description=r.description or "",
        mime_type=r.mime_type or "",
    )


def resource_contents_to_proto(
    content: types.TextResourceContents | types.BlobResourceContents,
) -> Any | None:
    """Blob content is base64-decoded from the MCP string into raw bytes for the proto
    bytes field.
    """
    if isinstance(content, types.TextResourceContents):
        return mcp_messages_pb2.ResourceContents(
            uri=content.uri,
            mime_type=content.mime_type or "",
            text=content.text,
        )
    if isinstance(content, types.BlobResourceContents):
        return mcp_messages_pb2.ResourceContents(
            uri=content.uri,
            mime_type=content.mime_type or "",
            blob=base64.b64decode(content.blob),
        )
    return None


def resource_template_to_proto(t: types.ResourceTemplate) -> Any:
    return mcp_messages_pb2.ResourceTemplate(
        uri_template=t.uri_template,
        name=t.name,
        title=t.title or "",
        description=t.description or "",
        mime_type=t.mime_type or "",
    )


def prompt_to_proto(p: types.Prompt) -> Any:
    args = [
        mcp_messages_pb2.Prompt.Argument(
            name=a.name,
            description=a.description or "",
            required=a.required or False,
        )
        for a in (p.arguments or [])
    ]
    return mcp_messages_pb2.Prompt(
        name=p.name,
        title=p.title or "",
        description=p.description or "",
        arguments=args,
    )


def prompt_message_to_proto(msg: types.PromptMessage) -> Any | None:
    role = (
        mcp_messages_pb2.ROLE_USER
        if msg.role == "user"
        else mcp_messages_pb2.ROLE_ASSISTANT
    )
    content = msg.content
    if isinstance(content, types.TextContent):
        return mcp_messages_pb2.PromptMessage(
            role=role,
            text=mcp_messages_pb2.TextContent(text=content.text),
        )
    if isinstance(content, types.ImageContent):
        return mcp_messages_pb2.PromptMessage(
            role=role,
            image=mcp_messages_pb2.ImageContent(
                data=content.data, mime_type=content.mimeType
            ),
        )
    if isinstance(content, types.AudioContent):
        return mcp_messages_pb2.PromptMessage(
            role=role,
            audio=mcp_messages_pb2.AudioContent(
                data=content.data, mime_type=content.mimeType
            ),
        )
    return None  # EmbeddedResource not supported in this transport


# ---------------------------------------------------------------------------
# proto → dict  (dicts that ClientSession / pydantic model_validate accepts)
# ---------------------------------------------------------------------------


def proto_tool_to_dict(t: Any) -> dict[str, Any]:
    tool: dict[str, Any] = {
        "name": t.name,
        "description": t.description or "",
        "inputSchema": MessageToDict(t.input_schema),
    }
    if t.title:
        tool["title"] = t.title
    if t.HasField("output_schema"):
        tool["outputSchema"] = MessageToDict(t.output_schema)
    return tool


def proto_call_content_to_dict(c: Any) -> dict[str, Any] | None:
    if c.HasField("text"):
        return {"type": "text", "text": c.text.text}
    if c.HasField("image"):
        return {
            "type": "image",
            "data": c.image.data.decode(),
            "mimeType": c.image.mime_type,
        }
    if c.HasField("audio"):
        return {
            "type": "audio",
            "data": c.audio.data.decode(),
            "mimeType": c.audio.mime_type,
        }
    return None


def proto_resource_to_dict(r: Any) -> dict[str, Any]:
    resource: dict[str, Any] = {"uri": r.uri, "name": r.name}
    if r.title:
        resource["title"] = r.title
    if r.description:
        resource["description"] = r.description
    if r.mime_type:
        resource["mimeType"] = r.mime_type
    return resource


def proto_resource_contents_to_dict(c: Any) -> dict[str, Any] | None:
    """Convert a ResourceContents proto to a dict.

    Blob bytes are base64-encoded back to string for MCP's BlobResourceContents.
    Returns None if neither text nor blob is set.
    """
    if c.text:
        item: dict[str, Any] = {"uri": c.uri, "text": c.text}
        if c.mime_type:
            item["mimeType"] = c.mime_type
        return item
    if c.blob:
        item = {"uri": c.uri, "blob": base64.b64encode(c.blob).decode()}
        if c.mime_type:
            item["mimeType"] = c.mime_type
        return item
    return None


def proto_resource_template_to_dict(t: Any) -> dict[str, Any]:
    tmpl: dict[str, Any] = {"uriTemplate": t.uri_template, "name": t.name}
    if t.title:
        tmpl["title"] = t.title
    if t.description:
        tmpl["description"] = t.description
    if t.mime_type:
        tmpl["mimeType"] = t.mime_type
    return tmpl


def proto_prompt_to_dict(p: Any) -> dict[str, Any]:
    prompt: dict[str, Any] = {"name": p.name}
    if p.title:
        prompt["title"] = p.title
    if p.description:
        prompt["description"] = p.description
    if p.arguments:
        prompt["arguments"] = [
            {
                "name": a.name,
                "description": a.description or "",
                "required": a.required,
            }
            for a in p.arguments
        ]
    return prompt


def proto_prompt_message_to_dict(msg: Any) -> dict[str, Any] | None:
    role = "user" if msg.role == mcp_messages_pb2.ROLE_USER else "assistant"
    if msg.HasField("text"):
        content: dict[str, Any] = {"type": "text", "text": msg.text.text}
    elif msg.HasField("image"):
        content = {
            "type": "image",
            "data": msg.image.data.decode(),
            "mimeType": msg.image.mime_type,
        }
    elif msg.HasField("audio"):
        content = {
            "type": "audio",
            "data": msg.audio.data.decode(),
            "mimeType": msg.audio.mime_type,
        }
    else:
        return None  # EmbeddedResource not supported in this transport
    return {"role": role, "content": content}
