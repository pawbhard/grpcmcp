# gRPC MCP Examples

Each subdirectory is a self-contained example with a `server.py` and a `client.py`.

| Example | What it demonstrates |
|---------|----------------------|
| `tools/` | Tool calls with progress reporting (`slow_count`) |
| `resources/` | Static resources and URI-template resources (notes store) |
| `prompts/` | Prompts with arguments and argument completion |

## Running an example

Start the server in one terminal, then run the client in another.

```bash
# tools
uv run example/tools/server.py
uv run example/tools/client.py

# resources
uv run example/resources/server.py
uv run example/resources/client.py

# prompts
uv run example/prompts/server.py
uv run example/prompts/client.py
```

All servers start on `localhost:50051` with gRPC reflection enabled.

## Test with grpcurl

Install [grpcurl](https://github.com/fullstorydev/grpcurl/releases) if you don't have it.

```bash
# list services
grpcurl -plaintext localhost:50051 list

# list tools
grpcurl -plaintext localhost:50051 model_context_protocol.Mcp/ListTools

# call a tool
grpcurl -plaintext \
  -d '{"request": {"name": "slow_count", "arguments": {"n": 3}}}' \
  localhost:50051 model_context_protocol.Mcp/CallTool

# list resources
grpcurl -plaintext localhost:50051 model_context_protocol.Mcp/ListResources

# list prompts
grpcurl -plaintext localhost:50051 model_context_protocol.Mcp/ListPrompts
```

## Server reflection

Reflection is opt-in. Enable it by passing `enable_reflection=True` to `serve_grpc`:

```python
asyncio.run(serve_grpc(mcp, enable_reflection=True))
```

All example servers have reflection enabled. When reflection is disabled, `grpcurl`
requires proto files passed explicitly — obtainable from
[mcp-grpc-transport-proto](https://github.com/GoogleCloudPlatform/mcp-grpc-transport-proto).
