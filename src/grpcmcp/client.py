import asyncio
import logging
from typing import Any

import anyio
import grpc
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct  # pylint: disable=no-name-in-module
from mcp import types
from mcp.shared.dispatcher import OnErrorFn, OnNotificationFn, OnRequestFn
from mcp.shared.exceptions import MCPError
from mcp.types import ErrorData, RequestId
from mcp_transport_proto import (
    mcp_messages_pb2,  # pylint: disable=no-member
    mcp_pb2_grpc,
)

from grpcmcp import proto_util

logger = logging.getLogger(__name__)


class GRPCClientDispatcher:
    """Implements the Dispatcher protocol over gRPC (client side).

    Maps MCP method strings to the appropriate gRPC stub calls and converts
    proto responses back into the dicts that ClientSession validates.

    Usage::

        dispatcher = GRPCClientDispatcher("localhost", 50051)
        async with ClientSession(dispatcher=dispatcher) as session:
            tools = await session.list_tools()
            result = await session.call_tool("my_tool", {"x": 1})
    """

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._stub: mcp_pb2_grpc.McpStub | None = None
        self._on_error: OnErrorFn | None = None
        self._ready = asyncio.Event()

    # --- Dispatcher protocol ---

    def set_handlers(
        self,
        on_request: OnRequestFn,  # pylint: disable=unused-argument
        on_notification: OnNotificationFn,  # pylint: disable=unused-argument
        on_error: OnErrorFn,
    ) -> None:
        # on_request / on_notification are never triggered — the gRPC server
        # does not push requests to the client in this transport design.
        self._on_error = on_error

    async def run(self) -> None:
        """Create the gRPC channel for the session lifetime, then sleep."""
        addr = f"{self._host}:{self._port}"
        logger.info("Connecting to gRPC server at %s", addr)
        channel = grpc.aio.insecure_channel(addr)
        self._stub = mcp_pb2_grpc.McpStub(channel)
        self._ready.set()
        logger.info("gRPC channel ready")
        try:
            await anyio.sleep_forever()
        finally:
            self._ready.clear()
            self._stub = None
            await channel.close()
            logger.info("gRPC channel closed")

    async def send_request(
        self,
        request_id: RequestId | None,  # pylint: disable=unused-argument
        request: dict[str, Any],
        metadata: Any = None,  # pylint: disable=unused-argument
        timeout: float | None = None,
    ) -> dict[str, Any]:
        await self._ready.wait()
        method = request["method"]
        params = request.get("params") or {}

        if method == "tools/list":
            return await self._list_tools(params, timeout)
        if method == "tools/call":
            return await self._call_tool(params, timeout)
        if method == "resources/list":
            return await self._list_resources(params, timeout)
        if method == "resources/read":
            return await self._read_resource(params, timeout)
        if method == "resources/templates/list":
            return await self._list_resource_templates(params, timeout)
        if method == "prompts/list":
            return await self._list_prompts(params, timeout)
        if method == "prompts/get":
            return await self._get_prompt(params, timeout)
        if method == "completion/complete":
            return await self._complete(params, timeout)
        raise MCPError(
            code=types.METHOD_NOT_FOUND,
            message=f"gRPC transport does not support method {method!r}",
        )

    async def send_notification(
        self,
        notification: dict[str, Any],
        related_request_id: RequestId | None = None,
    ) -> None:
        pass  # No persistent gRPC stream for client-initiated notifications

    # --- gRPC call handlers ---

    async def _list_tools(
        self, params: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        logger.info("Sending ListTools request")
        response = await self._stub.ListTools(  # type: ignore[union-attr]
            mcp_messages_pb2.ListToolsRequest(), timeout=timeout
        )
        logger.info("ListTools response received: %d tool(s)", len(response.tools))
        return {"tools": [proto_util.proto_tool_to_dict(t) for t in response.tools]}

    async def _call_tool(
        self, params: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        name = params["name"]
        arguments = params.get("arguments") or {}
        logger.info("Sending CallTool request: tool=%r arguments=%r", name, arguments)
        args_struct = Struct()
        ParseDict(arguments, args_struct)

        inner = mcp_messages_pb2.CallToolRequest.Request(
            name=name, arguments=args_struct
        )
        grpc_request = mcp_messages_pb2.CallToolRequest(request=inner)
        response = await self._stub.CallTool(  # type: ignore[union-attr]
            grpc_request, timeout=timeout
        )

        content = [
            d
            for c in response.content
            if (d := proto_util.proto_call_content_to_dict(c)) is not None
        ]

        result: dict[str, Any] = {"content": content, "isError": response.is_error}
        if response.HasField("structured_content"):
            result["structuredContent"] = MessageToDict(response.structured_content)
        logger.info("CallTool %r completed is_error=%s", name, response.is_error)
        return result

    async def _list_resources(
        self, params: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        logger.info("Sending ListResources request")
        response = await self._stub.ListResources(  # type: ignore[union-attr]
            mcp_messages_pb2.ListResourcesRequest(), timeout=timeout
        )
        logger.info(
            "ListResources response received: %d resource(s)", len(response.resources)
        )
        return {
            "resources": [
                proto_util.proto_resource_to_dict(r) for r in response.resources
            ]
        }

    async def _read_resource(
        self, params: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        uri = params["uri"]
        logger.info("Sending ReadResource request: uri=%r", uri)
        response = await self._stub.ReadResource(  # type: ignore[union-attr]
            mcp_messages_pb2.ReadResourceRequest(uri=uri), timeout=timeout
        )
        logger.info(
            "ReadResource response received: %d content(s)", len(response.resource)
        )
        contents = [
            d
            for c in response.resource
            if (d := proto_util.proto_resource_contents_to_dict(c)) is not None
        ]
        return {"contents": contents}

    async def _list_resource_templates(
        self, params: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        logger.info("Sending ListResourceTemplates request")
        response = await self._stub.ListResourceTemplates(  # type: ignore[union-attr]
            mcp_messages_pb2.ListResourceTemplatesRequest(), timeout=timeout
        )
        logger.info(
            "ListResourceTemplates response received: %d template(s)",
            len(response.resource_templates),
        )
        return {
            "resourceTemplates": [
                proto_util.proto_resource_template_to_dict(t)
                for t in response.resource_templates
            ]
        }

    async def _list_prompts(
        self, params: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        logger.info("Sending ListPrompts request")
        response = await self._stub.ListPrompts(  # type: ignore[union-attr]
            mcp_messages_pb2.ListPromptsRequest(), timeout=timeout
        )
        logger.info(
            "ListPrompts response received: %d prompt(s)", len(response.prompts)
        )
        return {
            "prompts": [proto_util.proto_prompt_to_dict(p) for p in response.prompts]
        }

    async def _get_prompt(
        self, params: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        name = params["name"]
        arguments = params.get("arguments") or {}
        logger.info("Sending GetPrompt request: name=%r arguments=%r", name, arguments)
        grpc_request = mcp_messages_pb2.GetPromptRequest(name=name)
        grpc_request.arguments.update(arguments)
        response = await self._stub.GetPrompt(  # type: ignore[union-attr]
            grpc_request, timeout=timeout
        )
        logger.info(
            "GetPrompt %r response received: %d message(s)",
            name,
            len(response.messages),
        )
        messages = [
            d
            for msg in response.messages
            if (d := proto_util.proto_prompt_message_to_dict(msg)) is not None
        ]
        result: dict[str, Any] = {"messages": messages}
        if response.description:
            result["description"] = response.description
        return result

    async def _complete(
        self, params: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        logger.info("Sending Complete request")
        ref = params["ref"]
        argument = params["argument"]
        grpc_argument = mcp_messages_pb2.CompletionRequest.Argument(
            name=argument["name"], value=argument["value"]
        )
        if ref.get("type") == "ref/prompt":
            grpc_request = mcp_messages_pb2.CompletionRequest(
                prompt_reference=mcp_messages_pb2.PromptReference(name=ref["name"]),
                argument=grpc_argument,
            )
        else:
            grpc_request = mcp_messages_pb2.CompletionRequest(
                resource_reference=mcp_messages_pb2.ResourceReference(uri=ref["uri"]),
                argument=grpc_argument,
            )
        response = await self._stub.Complete(  # type: ignore[union-attr]
            grpc_request, timeout=timeout
        )
        logger.info("Complete response received: %d value(s)", len(response.values))
        return {
            "completion": {
                "values": list(response.values),
                "total": response.total_matches,
                "hasMore": response.has_more,
            }
        }
