import asyncio
from typing import Any, Optional

from mcp.server.session import ServerSession
from mcp.types import LoggingLevel


class GRPCSessionAdapter(ServerSession):
    """
    Adapts gRPC stream to the interface expected by MCP Server.
    
    This adapter mimics a ServerSession but bypasses the standard MCP transport
    mechanism (streams, initialization) and directly sends notifications via a
    gRPC response queue.
    """
    def __init__(self, response_queue: asyncio.Queue):
        # We deliberately do NOT call super().__init__ because we function as a
        # stateless/streamless adapter for the purpose of the context.
        self.response_queue = response_queue

    async def send_log_message(
        self,
        level: LoggingLevel,
        data: Any,
        logger: Optional[str] = None,
        related_request_id: Optional[Any] = None,
    ) -> None:
        ...

    # Implement other methods as no-ops or raising NotImplementedError
    async def list_roots(self, *args, **kwargs):
        raise NotImplementedError("list_roots not implemented for gRPC transport yet")

    async def create_message(self, *args, **kwargs):
        raise NotImplementedError("sampling not implemented for gRPC transport yet")

    async def elicit(self, *args, **kwargs):
        raise NotImplementedError("elicitation not implemented for gRPC transport yet")

