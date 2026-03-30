import logging
from typing import Any

import grpc
import mcp.types as types
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Struct  # pylint: disable=no-name-in-module
from mcp_transport_proto import mcp_messages_pb2 as mcp_pb2  # pylint: disable=no-member
from mcp_transport_proto import mcp_pb2_grpc

from .proto_util import proto_to_call_tool_result, proto_to_tool

logger = logging.getLogger(__name__)


class GRPCClient:
    """Async gRPC client for an MCP server.

    Usage::

        async with GRPCClient("localhost", 50051) as client:
            tools = await client.list_tools()
            result = await client.call_tool("my_tool", {"x": 1})
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: float | None = None,
        channel_options: list[tuple[str, Any]] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._channel_options = channel_options
        self._channel: grpc.aio.Channel | None = None
        self._stub: mcp_pb2_grpc.McpStub | None = None

    async def __aenter__(self) -> "GRPCClient":
        self._channel = grpc.aio.insecure_channel(
            f"{self._host}:{self._port}",
            options=self._channel_options or [],
        )
        self._stub = mcp_pb2_grpc.McpStub(self._channel)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._channel:
            await self._channel.close()

    def _effective_timeout(self, per_call: float | None) -> float | None:
        return per_call if per_call is not None else self._timeout

    async def list_tools(
        self, *, timeout: float | None = None
    ) -> types.ListToolsResult:
        logger.debug("list_tools")
        response = await self._stub.ListTools(
            mcp_pb2.ListToolsRequest(), timeout=self._effective_timeout(timeout)
        )
        tools = [proto_to_tool(t) for t in response.tools]
        logger.debug("list_tools: %d tools", len(tools))
        return types.ListToolsResult(tools=tools)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> types.CallToolResult:
        logger.debug("call_tool %s", name)
        args_struct = Struct()
        if arguments:
            ParseDict(arguments, args_struct)
        request = mcp_pb2.CallToolRequest(
            request=mcp_pb2.CallToolRequest.Request(
                name=name,
                arguments=args_struct,
            )
        )
        response = await self._stub.CallTool(
            request, timeout=self._effective_timeout(timeout)
        )
        result = proto_to_call_tool_result(response)
        logger.debug("call_tool %s: isError=%s", name, result.isError)
        return result
