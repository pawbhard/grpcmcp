from typing import Any, Generic

from google.protobuf.json_format import MessageToDict
from mcp.shared.context import RequestContext, SessionT
from mcp.types import RequestParams


class GRPCRequestContext(RequestContext[SessionT, Any, Any], Generic[SessionT]):
    @classmethod
    def from_grpc(
        cls,
        request: Any,  # gRPC request object
        session: SessionT,
    ) -> "GRPCRequestContext[SessionT]":
        """Create a RequestContext from a gRPC request."""
        
        # Extract common fields if present
        common = getattr(request, "common", None)
        meta_dict: dict[str, Any] = {}
        
        if common:
            # simple mapping of progress token
            if common.HasField("progress"):
                 meta_dict["progressToken"] = common.progress.progress_token

            # Map arbitrary metadata
        # Map arbitrary metadata
            if common.HasField("metadata"):
                 meta_dict.update(MessageToDict(common.metadata))
        
        # Create RequestParams.Meta
        meta = RequestParams.Meta(**meta_dict)

        # Mock a request object that satisfies FastMCP's dependency injection
        # specifically fastmcp.server.dependencies.get_access_token 
        # which expects request.scope
        class MockRequest:
            def __init__(self):
                self.scope = {"type": "grpc", "user": None}
                self.headers = {}
        
        # We don't have a task_id concept yet in the same way, or lifespan context here
        return cls(
            request_id="grpc-request", 
            # gRPC doesn't inherently have a request ID per call unless we add one
            meta=meta,
            session=session,
            lifespan_context={},
            request=MockRequest()
        )
