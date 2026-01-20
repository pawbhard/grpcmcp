import asyncio
from typing import Any, Optional

from fastmcp.server.context import LogData
from mcp.server.session import ServerSession
from mcp.types import LoggingLevel


class GRPCSessionAdapter(ServerSession):
    """
    Adapts gRPC stream to the interface expected by FastMCP Context and Middleware.
    """
    def __init__(self, response_queue: asyncio.Queue):
        self.response_queue = response_queue
        # Dummy attributes to satisfy some SDK expectations if any
        self._fastmcp_state_prefix = "grpc-session"

    async def send_progress_notification(
        self,
        progress_token: str | int,
        progress: float,
        total: Optional[float] = None,
        message: Optional[str] = None,
        related_request_id: Optional[Any] = None,
    ) -> None:
        from .proto import mcp_pb2
        
        notification = mcp_pb2.ProgressNotification(
            progress_token=progress_token,
            progress=progress,
            total=total if total is not None else 0.0,
            message=message if message is not None else "",
        )
        
        # In gRPC, progress is often sent as a frame in the stream
        # For CallTool, it's part of CallToolResponse.common.progress
        response = mcp_pb2.CallToolResponse(
            common=mcp_pb2.ResponseFields(
                progress=notification
            )
        )
        await self.response_queue.put(response)

    async def send_log_message(
        self,
        level: LoggingLevel,
        data: LogData,
        logger: Optional[str] = None,
        related_request_id: Optional[Any] = None,
    ) -> None:
        from google.protobuf.json_format import ParseDict
        from google.protobuf.struct_pb2 import Value

        from .proto import mcp_pb2
        
        # Map LoggingLevel to LogLevel enum in proto
        log_level_map = {
            "debug": mcp_pb2.LOG_LEVEL_DEBUG,
            "info": mcp_pb2.LOG_LEVEL_INFO,
            "notice": mcp_pb2.LOG_LEVEL_NOTICE,
            "warning": mcp_pb2.LOG_LEVEL_WARNING,
            "error": mcp_pb2.LOG_LEVEL_ERROR,
            "critical": mcp_pb2.LOG_LEVEL_CRITICAL,
            "alert": mcp_pb2.LOG_LEVEL_ALERT,
            "emergency": mcp_pb2.LOG_LEVEL_EMERGENCY,
        }
        
        # LogData msg can be a string or a dict
        log_data_value = Value()
        if isinstance(data.msg, str):
            log_data_value.string_value = data.msg
        else:
            ParseDict(data.msg, log_data_value)
        
        log_message = mcp_pb2.LogMessage(
            log_level=log_level_map.get(level, mcp_pb2.LOG_LEVEL_INFO),
            logger=logger if logger else "",
            data=log_data_value
        )
        
        response = mcp_pb2.CallToolResponse(
            common=mcp_pb2.ResponseFields(
                log_message=log_message
            )
        )
        await self.response_queue.put(response)

    # Implement other methods as no-ops or raising NotImplementedError for now
    async def list_roots(self, *args, **kwargs):
        raise NotImplementedError("list_roots not implemented for gRPC transport yet")

    async def create_message(self, *args, **kwargs):
        raise NotImplementedError("sampling not implemented for gRPC transport yet")

    async def elicit(self, *args, **kwargs):
        raise NotImplementedError("elicitation not implemented for gRPC transport yet")

    async def send_notification(self, *args, **kwargs):
        # Could be used for ToolListChanged etc.
        pass
    
    def check_client_capability(self, capability: Any) -> bool:
        # Assume all capabilities for now or implement properly
        return True
