import os
import json
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.types as types
from supabase import create_client, Client
from datetime import datetime

# 初始化MCP服务器
app = Server("mcp-bridge")

# 从环境变量读取Supabase配置
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("Missing Supabase environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

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

if __name__ == "__main__":
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route

    async def handle_sse(request):
        async with SseServerTransport("/messages") as transport:
            await app.run(transport.read_stream, transport.write_stream, app.create_initialization_options())

    starlette_app = Starlette(routes=[
        Route("/sse", async def handle_sse(request):
    from mcp.server.sse import SseServerTransport
    transport = SseServerTransport("/messages")
    
    async with transport.connect_sse(
        request.scope,
        request.receive,
        request._send
    ) as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )),
    ])

    uvicorn.run(starlette_app, host="0.0.0.0", port=8000)
