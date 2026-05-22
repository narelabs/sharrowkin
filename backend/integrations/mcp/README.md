# MCP Integration for Sharrowkin Agent

Model Context Protocol (MCP) integration extracted from Google Antigravity SDK.

## Overview

MCP allows connecting external tool servers to Sharrowkin Agent. This enables:
- GitHub integration (issues, PRs, code search)
- Slack integration (messages, channels)
- Database tools (PostgreSQL, MySQL)
- Custom tool servers

## Installation

MCP is an **optional dependency**. Install it only if you need external tool servers:

```bash
pip install mcp
```

## Usage

### Basic Example

```python
from integrations.mcp import McpBridge
from core.tool_system import ToolRunner

# Create bridge
bridge = McpBridge()

# Connect to GitHub MCP server (stdio)
await bridge.connect_stdio(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"]
)

# Register MCP tools with ToolRunner
tool_runner = ToolRunner()
for tool in bridge.tools:
    tool_runner.register(tool)

# Use tools
result = await tool_runner.execute("github_search_issues", query="bug")
```

### Configuration via sharrowkin.yaml

```yaml
mcp_servers:
  - name: github
    type: stdio
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-github"
    
  - name: slack
    type: sse
    url: https://slack-mcp.example.com/sse
    headers:
      Authorization: "Bearer YOUR_TOKEN"
    
  - name: database
    type: http
    url: https://db-mcp.example.com
    timeout: 30.0
    sse_read_timeout: 300.0
```

### Connection Types

#### 1. Stdio (Local Process)

For local MCP servers that run as child processes:

```python
await bridge.connect_stdio(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"]
)
```

**Use cases:**
- GitHub MCP server
- Local database tools
- File system tools

#### 2. SSE (Server-Sent Events)

For remote MCP servers over HTTP with SSE:

```python
await bridge.connect_sse(
    url="https://mcp-server.example.com/sse",
    headers={"Authorization": "Bearer TOKEN"}
)
```

**Use cases:**
- Cloud-hosted MCP servers
- Shared team tools
- Enterprise integrations

#### 3. HTTP (Streamable HTTP)

For remote MCP servers with full HTTP streaming:

```python
await bridge.connect_streamable_http(
    url="https://mcp-server.example.com",
    headers={"Authorization": "Bearer TOKEN"},
    timeout=30.0,
    sse_read_timeout=300.0,
    terminate_on_close=True
)
```

**Use cases:**
- High-performance remote tools
- Long-running operations
- Custom enterprise servers

## Available MCP Servers

### Official Servers

1. **GitHub** - `@modelcontextprotocol/server-github`
   - Search issues, PRs
   - Create/update issues
   - Code search
   - Repository info

2. **Slack** - `@modelcontextprotocol/server-slack`
   - Send messages
   - List channels
   - Search messages

3. **PostgreSQL** - `@modelcontextprotocol/server-postgres`
   - Execute queries
   - Schema inspection
   - Data manipulation

4. **Filesystem** - `@modelcontextprotocol/server-filesystem`
   - Read/write files
   - Directory listing
   - File search

### Community Servers

See [MCP Servers Registry](https://github.com/modelcontextprotocol/servers) for more.

## Integration with Sharrowkin

### Automatic Registration

```python
from backend.config import load_config
from integrations.mcp import McpBridge
from core.tool_system import ToolRunner

config = load_config("/path/to/workspace")

# Create tool runner
tool_runner = ToolRunner()

# Connect MCP servers from config
for server_cfg in config.mcp_servers:
    bridge = McpBridge()
    await bridge.connect(server_cfg)
    
    # Register all tools
    for tool in bridge.tools:
        tool_runner.register(tool)
```

### With Hooks System

```python
from core.hooks.runner import HookRunner
from core.hooks.policy import allow, deny

# Create hook runner with policies
hook_runner = HookRunner()

# Allow MCP tools but deny dangerous ones
hook_runner.add_policy(allow("github_*"))
hook_runner.add_policy(allow("slack_send_message"))
hook_runner.add_policy(deny("database_drop_table"))

# Use with tool runner
tool_runner = ToolRunner()
tool_runner.set_hook_runner(hook_runner)
```

## Error Handling

```python
try:
    bridge = McpBridge()
    await bridge.connect_stdio("npx", ["-y", "@modelcontextprotocol/server-github"])
except ImportError:
    print("MCP not installed. Install with: pip install mcp")
except Exception as e:
    print(f"Failed to connect to MCP server: {e}")
```

## Cleanup

Always cleanup MCP connections:

```python
# Manual cleanup
await bridge.stop()

# Or use as context manager (future enhancement)
async with McpBridge() as bridge:
    await bridge.connect_stdio("npx", ["-y", "@modelcontextprotocol/server-github"])
    # Use tools...
    # Automatic cleanup on exit
```

## Limitations

1. **Optional Dependency**: MCP must be installed separately
2. **Async Only**: All MCP operations are async
3. **No Sync Tools**: MCP tools cannot be used in sync contexts
4. **Connection Lifecycle**: Must manually manage connect/stop

## Troubleshooting

### ImportError: No module named 'mcp'

Install MCP:
```bash
pip install mcp
```

### Connection Timeout

Increase timeout for slow servers:
```python
await bridge.connect_streamable_http(
    url="https://slow-server.example.com",
    timeout=60.0,  # Increase from default 30s
    sse_read_timeout=600.0  # Increase from default 300s
)
```

### Tool Not Found

Check available tools:
```python
print("Available MCP tools:", [t.__name__ for t in bridge.tools])
```

## Architecture

```
┌─────────────────┐
│ Sharrowkin Agent│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   ToolRunner    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   McpBridge     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ClientSessionGroup│
└────────┬────────┘
         │
    ┌────┴────┬────────┬────────┐
    ▼         ▼        ▼        ▼
  stdio      SSE     HTTP    Custom
  Server    Server  Server   Server
```

## References

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Servers Registry](https://github.com/modelcontextprotocol/servers)
- [Google Antigravity SDK](https://github.com/google/antigravity-sdk-python)
