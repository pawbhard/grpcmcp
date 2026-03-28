# gRPC MCP Example Server

This example runs an MCP server over gRPC with server reflection enabled.

## Start the server

```bash
python example/grpc_example_server.py
```

The server starts on `localhost:50051`.

## Test with grpcurl

Install [grpcurl](https://github.com/fullstorydev/grpcurl/releases) if you don't have it.

### List available services

```bash
grpcurl -plaintext localhost:50051 list
```

Expected output:
```
grpc.reflection.v1alpha.ServerReflection
model_context_protocol.Mcp
```

### Describe the service

```bash
grpcurl -plaintext localhost:50051 describe model_context_protocol.Mcp
```

### List tools

```bash
grpcurl -plaintext localhost:50051 model_context_protocol.Mcp/ListTools
```

### Call a tool

```bash
grpcurl -plaintext \
  -d '{"request": {"name": "slow_count", "arguments": {"n": 3}}}' \
  localhost:50051 model_context_protocol.Mcp/CallTool
```

Expected output:
```json
{
  "content": [
    {
      "text": {
        "text": "Finished counting to 3"
      }
    }
  ],
  "structured_content": {
    "result": "Finished counting to 3"
  }
}
```

## Server reflection

Reflection is opt-in. Enable it by passing `enable_reflection=True` to `serve_grpc`:

```python
asyncio.run(serve_grpc(mcp, enable_reflection=True))
```

When disabled (the default), grpcurl requires `--proto` flags pointing to the proto files:

```bash
grpcurl -plaintext \
  -proto src/grpcmcp/proto/mcp.proto \
  -import-path src/grpcmcp/proto \
  localhost:50051 model_context_protocol.Mcp/ListTools
```
