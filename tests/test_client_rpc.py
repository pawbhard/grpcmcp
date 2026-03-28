"""Unit tests for GRPCClientDispatcher against a fake in-process gRPC servicer."""

# pylint: disable=unnecessary-dunder-call
import unittest

import grpc
from google.protobuf.struct_pb2 import Struct  # pylint: disable=no-name-in-module
from mcp.client.session import ClientSession
from mcp.types import TextContent, TextResourceContents
from mcp_transport_proto import (
    mcp_messages_pb2,  # pylint: disable=no-member
    mcp_pb2_grpc,
)

from grpcmcp.client import GRPCClientDispatcher


class FakeMcpServicer(mcp_pb2_grpc.McpServicer):
    """Minimal in-process servicer that returns hard-coded responses."""

    async def ListTools(self, _request, _context):  # pylint: disable=invalid-overridden-method
        input_schema = Struct()
        input_schema.update(
            {"type": "object", "properties": {"x": {"type": "integer"}}}
        )
        return mcp_messages_pb2.ListToolsResponse(
            tools=[
                mcp_messages_pb2.Tool(
                    name="fake_tool",
                    description="A fake tool",
                    input_schema=input_schema,
                )
            ]
        )

    async def CallTool(self, request, _context):  # pylint: disable=invalid-overridden-method
        tool_name = request.request.name
        return mcp_messages_pb2.CallToolResponse(
            content=[
                mcp_messages_pb2.CallToolResponse.Content(
                    text=mcp_messages_pb2.TextContent(text=f"called {tool_name}")
                )
            ],
            is_error=False,
        )

    async def ListResources(self, _request, _context):  # pylint: disable=invalid-overridden-method
        return mcp_messages_pb2.ListResourcesResponse(
            resources=[
                mcp_messages_pb2.Resource(
                    uri="fake://item",
                    name="item",
                    description="A fake resource",
                    mime_type="text/plain",
                )
            ]
        )

    async def ReadResource(self, request, _context):  # pylint: disable=invalid-overridden-method
        return mcp_messages_pb2.ReadResourceResponse(
            resource=[
                mcp_messages_pb2.ResourceContents(
                    uri=request.uri,
                    mime_type="text/plain",
                    text="fake content",
                )
            ]
        )

    async def ListResourceTemplates(self, _request, _context):  # pylint: disable=invalid-overridden-method
        return mcp_messages_pb2.ListResourceTemplatesResponse(
            resource_templates=[
                mcp_messages_pb2.ResourceTemplate(
                    uri_template="fake://{id}",
                    name="fake_template",
                    description="A fake template",
                )
            ]
        )

    async def ListPrompts(self, _request, _context):  # pylint: disable=invalid-overridden-method
        return mcp_messages_pb2.ListPromptsResponse(
            prompts=[
                mcp_messages_pb2.Prompt(
                    name="fake_prompt",
                    description="A fake prompt",
                    arguments=[
                        mcp_messages_pb2.Prompt.Argument(
                            name="topic", description="The topic", required=True
                        )
                    ],
                )
            ]
        )

    async def GetPrompt(self, request, _context):  # pylint: disable=invalid-overridden-method
        topic = request.arguments.get("topic", "world")
        return mcp_messages_pb2.GetPromptResponse(
            description="A fake prompt response",
            messages=[
                mcp_messages_pb2.PromptMessage(
                    role=mcp_messages_pb2.ROLE_USER,
                    text=mcp_messages_pb2.TextContent(text=f"Tell me about {topic}"),
                )
            ],
        )

    async def Complete(self, request, _context):  # pylint: disable=invalid-overridden-method
        prefix = request.argument.value
        suggestions = [w for w in ["alpha", "beta", "gamma"] if w.startswith(prefix)]
        return mcp_messages_pb2.CompletionResponse(
            values=suggestions,
            total_matches=len(suggestions),
            has_more=False,
        )


class TestClientRPC(unittest.IsolatedAsyncioTestCase):
    """Test GRPCClientDispatcher against a fake gRPC servicer."""

    async def asyncSetUp(self):
        self.grpc_server = grpc.aio.server()
        mcp_pb2_grpc.add_McpServicer_to_server(FakeMcpServicer(), self.grpc_server)
        port = self.grpc_server.add_insecure_port("localhost:0")
        await self.grpc_server.start()

        self.dispatcher = GRPCClientDispatcher("localhost", port)
        self._session = ClientSession(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            dispatcher=self.dispatcher,
        )
        await self._session.__aenter__()

    async def asyncTearDown(self):
        await self._session.__aexit__(None, None, None)
        await self.grpc_server.stop(None)

    # --- Tools ---

    async def test_list_tools(self):
        result = await self._session.list_tools()
        self.assertEqual(len(result.tools), 1)
        self.assertEqual(result.tools[0].name, "fake_tool")
        self.assertEqual(result.tools[0].description, "A fake tool")

    async def test_call_tool(self):
        result = await self._session.call_tool("fake_tool", {"x": 42})
        self.assertFalse(result.is_error)
        self.assertEqual(len(result.content), 1)
        self.assertIsInstance(result.content[0], TextContent)
        self.assertEqual(result.content[0].text, "called fake_tool")

    # --- Resources ---

    async def test_list_resources(self):
        result = await self._session.list_resources()
        self.assertEqual(len(result.resources), 1)
        r = result.resources[0]
        self.assertEqual(r.uri, "fake://item")
        self.assertEqual(r.name, "item")
        self.assertEqual(r.description, "A fake resource")

    async def test_read_resource(self):
        result = await self._session.read_resource("fake://item")  # type: ignore[arg-type]
        self.assertEqual(len(result.contents), 1)
        self.assertIsInstance(result.contents[0], TextResourceContents)
        self.assertEqual(result.contents[0].text, "fake content")

    async def test_list_resource_templates(self):
        result = await self._session.list_resource_templates()
        self.assertEqual(len(result.resource_templates), 1)
        t = result.resource_templates[0]
        self.assertEqual(t.uri_template, "fake://{id}")
        self.assertEqual(t.name, "fake_template")

    # --- Prompts ---

    async def test_list_prompts(self):
        result = await self._session.list_prompts()
        self.assertEqual(len(result.prompts), 1)
        p = result.prompts[0]
        self.assertEqual(p.name, "fake_prompt")
        self.assertEqual(p.description, "A fake prompt")
        self.assertTrue(any(a.name == "topic" for a in (p.arguments or [])))

    async def test_get_prompt(self):
        result = await self._session.get_prompt("fake_prompt", {"topic": "gRPC"})
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.messages[0].role, "user")
        self.assertIsInstance(result.messages[0].content, TextContent)
        self.assertEqual(result.messages[0].content.text, "Tell me about gRPC")  # type: ignore[union-attr]

    # --- Completion ---

    async def test_complete(self):
        result = await self._session.complete(
            ref={"type": "ref/prompt", "name": "fake_prompt"},  # type: ignore[arg-type]
            argument={"name": "topic", "value": "al"},  # type: ignore[arg-type]
        )
        self.assertIn("alpha", result.completion.values)

    async def test_complete_no_match(self):
        result = await self._session.complete(
            ref={"type": "ref/prompt", "name": "fake_prompt"},  # type: ignore[arg-type]
            argument={"name": "topic", "value": "zzz"},  # type: ignore[arg-type]
        )
        self.assertEqual(result.completion.values, [])


if __name__ == "__main__":
    unittest.main()
