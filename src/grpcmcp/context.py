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
            if common.HasField("metadata"):
                 meta_dict.update(MessageToDict(common.metadata))
        
        # Create RequestParams.Meta
        meta = RequestParams.Meta(**meta_dict)

        return cls(
            request_id="grpc-request", 
            meta=meta,
            session=session,
            lifespan_context={},
        )

