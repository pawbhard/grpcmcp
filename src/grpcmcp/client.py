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
        request_id: RequestId,  # pylint: disable=unused-argument
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

    async def send_response(
        self,
        request_id: RequestId,
        response: dict[str, Any] | ErrorData,
    ) -> None:
        raise NotImplementedError(
            "GRPCClientDispatcher does not handle server-initiated requests"
        )

    # --- gRPC call handlers ---

    async def _list_tools(
        self, params: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        logger.info("Sending ListTools request")
        response = await self._stub.ListTools(  # type: ignore[union-attr]
            mcp_messages_pb2.ListToolsRequest(), timeout=timeout
        )
        logger.info("ListTools response received: %d tool(s)", len(response.tools))

        tools = []
        for t in response.tools:
            tool: dict[str, Any] = {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": MessageToDict(t.input_schema),
            }
            if t.title:
                tool["title"] = t.title
            if t.HasField("output_schema"):
                tool["outputSchema"] = MessageToDict(t.output_schema)
            tools.append(tool)

        return {"tools": tools}

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

        content = []
        for c in response.content:
            if c.HasField("text"):
                content.append({"type": "text", "text": c.text.text})
            elif c.HasField("image"):
                content.append(
                    {
                        "type": "image",
                        "data": c.image.data.decode(),
                        "mimeType": c.image.mime_type,
                    }
                )
            elif c.HasField("audio"):
                content.append(
                    {
                        "type": "audio",
                        "data": c.audio.data.decode(),
                        "mimeType": c.audio.mime_type,
                    }
                )

        result: dict[str, Any] = {"content": content, "isError": response.is_error}
        if response.HasField("structured_content"):
            result["structuredContent"] = MessageToDict(response.structured_content)
        logger.info("CallTool %r completed is_error=%s", name, response.is_error)
        return result
