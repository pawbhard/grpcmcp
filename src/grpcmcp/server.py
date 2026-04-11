import asyncio
import logging
from typing import Any

import anyio
import grpc
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct  # pylint: disable=no-name-in-module
from grpc_reflection.v1alpha import reflection
from mcp import types
from mcp.server.mcpserver.server import MCPServer
from mcp.server.session import ServerSession
from mcp.shared.dispatcher import OnErrorFn, OnNotificationFn, OnRequestFn, ReplyHandle
from mcp.shared.exceptions import MCPError
from mcp.types import ErrorData, RequestId
from mcp_transport_proto import (
    mcp_messages_pb2,  # pylint: disable=no-member
    mcp_pb2,
    mcp_pb2_grpc,
)

from grpcmcp import proto_util

logger = logging.getLogger(__name__)


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
        request: dict[str, Any],
        metadata: Any = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "GRPCDispatcher does not initiate server-to-client requests"
        )

    async def send_notification(
        self,
        notification: dict[str, Any],
        related_reply_handle: ReplyHandle | None = None,
    ) -> None:
        pass  # No persistent gRPC stream for server-push notifications

    async def send_response(
        self,
        handle: ReplyHandle,
        response: dict[str, Any] | ErrorData,
    ) -> None:
        future: asyncio.Future[dict[str, Any] | ErrorData] = handle
        if not future.done():
            future.set_result(response)

    # --- Internal routing ---

    async def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route an MCP request through the session and await its response."""
        assert self._on_request is not None, (
            "Session not started; call set_handlers first"
        )
        self._counter += 1
        request_id = self._counter
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any] | ErrorData] = loop.create_future()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        await self._on_request(request_id, future, payload, None)
        try:
            result = await future
        except asyncio.CancelledError:
            raise
        if isinstance(result, ErrorData):
            raise MCPError(result.code, result.message, result.data)
        return result  # type: ignore[return-value]

    # --- gRPC servicer ---

    async def ListTools(self, request, _context):  # pylint: disable=invalid-overridden-method
        logger.info("ListTools request received")
        try:
            result_dict = await self._dispatch("tools/list", {})
            list_result = types.ListToolsResult.model_validate(result_dict)
            proto_tools = [proto_util.tool_to_proto(t) for t in list_result.tools]
            logger.info("ListTools returning %d tool(s)", len(proto_tools))
            return mcp_messages_pb2.ListToolsResponse(tools=proto_tools)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("ListTools failed")
            raise

    async def CallTool(self, request, _context):  # pylint: disable=invalid-overridden-method
        tool_name = request.request.name
        arguments = MessageToDict(request.request.arguments)
        logger.info("CallTool request: tool=%r arguments=%r", tool_name, arguments)
        try:
            result_dict = await self._dispatch(
                "tools/call", {"name": tool_name, "arguments": arguments}
            )
            call_result = types.CallToolResult.model_validate(result_dict)

            proto_contents = [
                p
                for c in call_result.content
                if (p := proto_util.call_content_to_proto(c)) is not None
            ]

            structured_content = None
            if call_result.structured_content:
                structured_content = Struct()
                ParseDict(call_result.structured_content, structured_content)

            logger.info(
                "CallTool %r completed is_error=%s",
                tool_name,
                call_result.is_error or False,
            )
            return mcp_messages_pb2.CallToolResponse(
                content=proto_contents,
                structured_content=structured_content,
                is_error=call_result.is_error or False,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("CallTool %r failed", tool_name)
            return mcp_messages_pb2.CallToolResponse(
                content=[
                    mcp_messages_pb2.CallToolResponse.Content(
                        text=mcp_messages_pb2.TextContent(text=str(e))
                    )
                ],
                is_error=True,
            )

    async def ListResources(self, request, _context):  # pylint: disable=invalid-overridden-method
        logger.info("ListResources request received")
        try:
            result_dict = await self._dispatch("resources/list", {})
            list_result = types.ListResourcesResult.model_validate(result_dict)
            proto_resources = [
                proto_util.resource_to_proto(r) for r in list_result.resources
            ]
            logger.info("ListResources returning %d resource(s)", len(proto_resources))
            return mcp_messages_pb2.ListResourcesResponse(resources=proto_resources)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("ListResources failed")
            raise

    async def ReadResource(self, request, _context):  # pylint: disable=invalid-overridden-method
        uri = request.uri
        logger.info("ReadResource request: uri=%r", uri)
        try:
            result_dict = await self._dispatch("resources/read", {"uri": uri})
            read_result = types.ReadResourceResult.model_validate(result_dict)
            proto_contents = [
                p
                for c in read_result.contents
                if (p := proto_util.resource_contents_to_proto(c)) is not None
            ]
            logger.info(
                "ReadResource %r returning %d content(s)", uri, len(proto_contents)
            )
            return mcp_messages_pb2.ReadResourceResponse(resource=proto_contents)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("ReadResource %r failed", uri)
            raise

    async def ListResourceTemplates(self, request, _context):  # pylint: disable=invalid-overridden-method
        logger.info("ListResourceTemplates request received")
        try:
            result_dict = await self._dispatch("resources/templates/list", {})
            list_result = types.ListResourceTemplatesResult.model_validate(result_dict)
            proto_templates = [
                proto_util.resource_template_to_proto(t)
                for t in list_result.resource_templates
            ]
            logger.info(
                "ListResourceTemplates returning %d template(s)", len(proto_templates)
            )
            return mcp_messages_pb2.ListResourceTemplatesResponse(
                resource_templates=proto_templates
            )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("ListResourceTemplates failed")
            raise

    async def ListPrompts(self, request, _context):  # pylint: disable=invalid-overridden-method
        logger.info("ListPrompts request received")
        try:
            result_dict = await self._dispatch("prompts/list", {})
            list_result = types.ListPromptsResult.model_validate(result_dict)
            proto_prompts = [proto_util.prompt_to_proto(p) for p in list_result.prompts]
            logger.info("ListPrompts returning %d prompt(s)", len(proto_prompts))
            return mcp_messages_pb2.ListPromptsResponse(prompts=proto_prompts)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("ListPrompts failed")
            raise

    async def GetPrompt(self, request, _context):  # pylint: disable=invalid-overridden-method
        name = request.name
        arguments = dict(request.arguments)
        logger.info("GetPrompt request: name=%r arguments=%r", name, arguments)
        try:
            result_dict = await self._dispatch(
                "prompts/get", {"name": name, "arguments": arguments}
            )
            get_result = types.GetPromptResult.model_validate(result_dict)
            proto_messages = [
                p
                for msg in get_result.messages
                if (p := proto_util.prompt_message_to_proto(msg)) is not None
            ]
            logger.info(
                "GetPrompt %r returning %d message(s)", name, len(proto_messages)
            )
            return mcp_messages_pb2.GetPromptResponse(
                description=get_result.description or "",
                messages=proto_messages,
            )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("GetPrompt %r failed", name)
            raise

    async def Complete(self, request, _context):  # pylint: disable=invalid-overridden-method
        logger.info("Complete request received")
        try:
            if request.HasField("prompt_reference"):
                ref: dict[str, Any] = {
                    "type": "ref/prompt",
                    "name": request.prompt_reference.name,
                }
            else:
                ref = {
                    "type": "ref/resource",
                    "uri": request.resource_reference.uri,
                }
            params: dict[str, Any] = {
                "ref": ref,
                "argument": {
                    "name": request.argument.name,
                    "value": request.argument.value,
                },
            }
            if request.HasField("context") and request.context.arguments:
                params["context"] = {"arguments": dict(request.context.arguments)}

            result_dict = await self._dispatch("completion/complete", params)
            complete_result = types.CompleteResult.model_validate(result_dict)
            completion = complete_result.completion
            logger.info("Complete returning %d value(s)", len(completion.values))
            return mcp_messages_pb2.CompletionResponse(
                values=completion.values,
                total_matches=completion.total or 0,
                has_more=completion.has_more or False,
            )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Complete failed")
            raise


async def serve_grpc(
    server: MCPServer,
    host: str = "0.0.0.0",
    port: int = 50051,
    enable_reflection: bool = False,
) -> None:
    lowlevel = server._lowlevel_server  # type: ignore[attr-defined]  # pylint: disable=protected-access
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
                service_name = mcp_pb2.DESCRIPTOR.services_by_name["Mcp"].full_name
                reflection.enable_server_reflection(
                    [service_name, reflection.SERVICE_NAME], grpc_server
                )
            listen_addr = f"{host}:{port}"
            grpc_server.add_insecure_port(listen_addr)
            logger.info("Starting gRPC server on %s", listen_addr)
            await grpc_server.start()
            logger.info("gRPC server started")

            async with anyio.create_task_group() as tg:
                tg.start_soon(grpc_server.wait_for_termination)
                async for message in session.incoming_messages:
                    tg.start_soon(
                        lowlevel._handle_message,  # type: ignore[attr-defined]  # pylint: disable=protected-access
                        message,
                        session,
                        lifespan_context,
                        False,
                    )
