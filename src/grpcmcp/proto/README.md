# Generating Protobuf Files

To regenerate the Python files from `mcp.proto`, run the following command from the project root (`grpcmcp` directory):

```bash
uv run python -m grpc_tools.protoc -Isrc/grpcmcp/proto --python_out=src --grpc_python_out=src src/grpcmcp/proto/*.proto
```

This will update:
- `src/grpcmcp/proto/mcp_pb2.py`
- `src/grpcmcp/proto/mcp_pb2_grpc.py`

**Note:** You may need to ensure `google.protobuf` dependencies are available.
