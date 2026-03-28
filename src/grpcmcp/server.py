import asyncio
from typing import Any

import anyio
import grpc
import mcp.types as types
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct
from grpc_reflection.v1alpha import reflection
from mcp.server.mcpserver.server import MCPServer
from mcp.server.session import ServerSession
from mcp.shared.dispatcher import OnErrorFn, OnNotificationFn, OnRequestFn
from mcp.shared.exceptions import MCPError
from mcp.types import ErrorData, RequestId

from mcp_transport_proto import mcp_messages_pb2 as mcp_pb2
from mcp_transport_proto import mcp_pb2 as mcp_service_pb2
from mcp_transport_proto import mcp_pb2_grpc


class GRPCDispatcher(mcp_pb2_grpc.McpServicer):
    """Implements the Dispatcher protocol over gRPC.

    Receives gRPC calls (ListTools, CallTool), routes them through the MCP
    session machinery via on_request, and resolves per-request futures when
    the session calls send_response.
    """

    def __init__(self) -> None:
        self._on_request: OnRequestFn | None = None
        self._on_notification: OnNotificationFn | None = None
        self._on_error: OnErrorFn | None = None
        self._pending: dict[RequestId, asyncio.Future[dict[str, Any] | ErrorData]] = {}
        self._counter = 0

    # --- Dispatcher protocol ---

    def set_handlers(
        self,
        on_request: OnRequestFn,
        on_notification: OnNotificationFn,
        on_error: OnErrorFn,
    ) -> None:
        self._on_request = on_request
        self._on_notification = on_notification
        self._on_error = on_error

    async def run(self) -> None:
        # gRPC calls arrive via servicer methods; no stream to poll.
        await anyio.sleep_forever()

    async def send_request(
        self,
        request_id: RequestId,
        request: dict[str, Any],
        metadata: Any = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("GRPCDispatcher does not initiate server-to-client requests")

    async def send_notification(
        self,
        notification: dict[str, Any],
        related_request_id: RequestId | None = None,
    ) -> None:
        pass  # No persistent gRPC stream for server-push notifications

    async def send_response(
        self,
        request_id: RequestId,
        response: dict[str, Any] | ErrorData,
    ) -> None:
        future = self._pending.pop(request_id, None)
        if future and not future.done():
            future.set_result(response)

    # --- Internal routing ---

    async def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route an MCP request through the session and await its response."""
        assert self._on_request is not None, "Session not started; call set_handlers first"
        self._counter += 1
        request_id = self._counter
        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict[str, Any] | ErrorData] = loop.create_future()
        self._pending[request_id] = future
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        await self._on_request(request_id, payload, None)
        result = await future
        if isinstance(result, ErrorData):
            raise MCPError(result.code, result.message, result.data)
        return result  # type: ignore[return-value]

    # --- gRPC servicer ---

    async def ListTools(self, request, context):
        try:
            result_dict = await self._dispatch("tools/list", {})
            list_result = types.ListToolsResult.model_validate(result_dict)

            proto_tools = []
            for tool in list_result.tools:
                input_schema = Struct()
                if tool.input_schema:
                    ParseDict(tool.input_schema, input_schema)

                output_schema = None
                if tool.output_schema:
                    output_schema = Struct()
                    ParseDict(tool.output_schema, output_schema)

                tool_kwargs: dict[str, Any] = {
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
        tool_name = request.request.name
        arguments = MessageToDict(request.request.arguments)
        try:
            result_dict = await self._dispatch(
                "tools/call", {"name": tool_name, "arguments": arguments}
            )
            call_result = types.CallToolResult.model_validate(result_dict)

            proto_contents = []
            for content in call_result.content:
                if isinstance(content, types.TextContent):
                    proto_contents.append(mcp_pb2.CallToolResponse.Content(
                        text=mcp_pb2.TextContent(text=content.text)
                    ))
                elif isinstance(content, types.ImageContent):
                    proto_contents.append(mcp_pb2.CallToolResponse.Content(
                        image=mcp_pb2.ImageContent(
                            data=content.data,
                            mime_type=content.mimeType,
                        )
                    ))

            structured_content = None
            if call_result.structured_content:
                structured_content = Struct()
                ParseDict(call_result.structured_content, structured_content)

            return mcp_pb2.CallToolResponse(
                content=proto_contents,
                structured_content=structured_content,
                is_error=call_result.is_error or False,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return mcp_pb2.CallToolResponse(
                content=[mcp_pb2.CallToolResponse.Content(
                    text=mcp_pb2.TextContent(text=str(e))
                )],
                is_error=True,
            )


async def serve_grpc(
    server: MCPServer,
    host: str = "0.0.0.0",
    port: int = 50051,
    enable_reflection: bool = False,
) -> None:
    lowlevel = server._lowlevel_server  # type: ignore[attr-defined]
    dispatcher = GRPCDispatcher()
    init_options = lowlevel.create_initialization_options()

    async with lowlevel.lifespan(lowlevel) as lifespan_context:
        # read_stream/write_stream are ignored when dispatcher is provided;
        # pass None until the fork makes them Optional in ServerSession.
        async with ServerSession(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            init_options,
            stateless=True,
            dispatcher=dispatcher,
        ) as session:
            grpc_server = grpc.aio.server()
            mcp_pb2_grpc.add_McpServicer_to_server(dispatcher, grpc_server)
            if enable_reflection:
                service_name = mcp_service_pb2.DESCRIPTOR.services_by_name["Mcp"].full_name
                reflection.enable_server_reflection([service_name, reflection.SERVICE_NAME], grpc_server)
            listen_addr = f"[::]:{port}"
            grpc_server.add_insecure_port(listen_addr)
            print(f"Starting gRPC server on {listen_addr}")
            await grpc_server.start()

            async with anyio.create_task_group() as tg:
                tg.start_soon(grpc_server.wait_for_termination)
                async for message in session.incoming_messages:
                    tg.start_soon(
                        lowlevel._handle_message,  # type: ignore[attr-defined]
                        message,
                        session,
                        lifespan_context,
                        False,
                    )
