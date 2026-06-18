import os
import json
import asyncio
from datetime import datetime

from mcp.server import Server
import mcp.types as types
from supabase import create_client
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response
from mcp.server.sse import SseServerTransport

# 初始化MCP服务器
app = Server("mcp-bridge")

# 从环境变量读取Supabase配置
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("Missing Supabase environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# 在函数外部定义 transport
transport = SseServerTransport("/messages")

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="read_logs",
            description="读取所有日志条目",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数上限", "default": 10}
                }
            }
        ),
        types.Tool(
            name="write_log",
            description="写入一条新日志",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "日志内容"}
                },
                "required": ["content"]
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "read_logs":
        limit = arguments.get("limit", 10)
        result = supabase.table("logs").select("*").order("created_at", desc=True).limit(limit).execute()
        return [types.TextContent(type="text", text=json.dumps(result.data, ensure_ascii=False, default=str))]

    elif name == "write_log":
        content = arguments.get("content")
        if not content:
            return [types.TextContent(type="text", text="错误：日志内容不能为空")]
        result = supabase.table("logs").insert({
            "content": content,
            "created_at": datetime.now().isoformat()
        }).execute()
        return [types.TextContent(type="text", text="日志写入成功")]

    raise ValueError(f"Unknown tool: {name}")

# 处理 SSE 连接
async def handle_sse(request):
    async with transport.connect_sse(
        request.scope,
        request.receive,
        request._send
    ) as streams:
        await app.run(
            streams[0],
            streams[1],
            app.create_initialization_options()
        )
    return Response(content="", headers={"Content-Type": "text/event-stream"})

# 处理 POST 消息请求
async def handle_messages(request):
    await transport.handle_post_message(request.scope, request.receive, request._send)
    return Response()

# 定义路由
starlette_app = Starlette(routes=[
    Route("/sse", handle_sse),
    Route("/messages", handle_messages, methods=["POST"]),
])

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
