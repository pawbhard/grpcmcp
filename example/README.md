# gRPC MCP Example

This example runs an MCP server over gRPC with server reflection enabled, and a matching client.

## Start the server

```bash
uv run example/grpc_example_server.py
```

The server starts on `0.0.0.0:50051` and exposes one tool: `slow_count`.

## Run the client

In a second terminal:

```bash
uv run example/grpc_example_client.py
```

Expected output:

```
Available tools (1):
  - slow_count: Counts to n slowly, reporting progress.

Calling tool 'slow_count' with n=3 ...
is_error: False
Result: Finished counting to 3
Structured: {'result': 'Finished counting to 3'}
```

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
  "structuredContent": {
    "result": "Finished counting to 3"
  }
}
```

## Server reflection

Reflection is opt-in. Enable it by passing `enable_reflection=True` to `serve_grpc`:

```python
asyncio.run(serve_grpc(mcp, enable_reflection=True))
```

The example server has reflection enabled by default. When reflection is disabled, `grpcurl` requires proto files to be passed explicitly — these can be obtained from [mcp-grpc-transport-proto](https://github.com/GoogleCloudPlatform/mcp-grpc-transport-proto).
