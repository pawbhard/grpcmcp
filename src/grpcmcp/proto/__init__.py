import os
import sys

# Add this directory to sys.path so that generated proto files can import each other
# (e.g., mcp_pb2_grpc.py imports mcp_messages_pb2)
proto_dir = os.path.dirname(__file__)
if proto_dir not in sys.path:
    sys.path.append(proto_dir)
