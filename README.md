# Codebase Time Machine

**Understand why code exists, not just what it does.**

Codebase Time Machine (CTM) answers the question developers ask daily: *"Why does this code exist?"* It traces the decision chain from code to commits, PRs, issues, and discussions.

**What used to take 10-30 minutes of manual git blame → PR → issue searching now takes less than a minute.**

## Two Ways to Use CTM

| | MCP Server | VS Code Extension |
|---|---|---|
| **For** | Claude Code, Claude Desktop | VS Code users |
| **Tools** | All 32 investigation tools | 10 curated core tools |
| **Interface** | Chat with AI | Right-click menu + Chat |
| **Setup** | [MCP Server Guide](ctm_mcp_server/README.md) | [Extension Guide](extensions/vscode/README.md) |

## Quick Start

### MCP Server (Claude Code / Claude Desktop)

```bash
pip install codebase-time-machine
```

Add to your MCP config:
```json
{
  "mcpServers": {
    "ctm": {
      "command": "python",
      "args": ["-m", "ctm_mcp_server.stdio_server"],
      "env": { "GITHUB_TOKEN": "optional" }
    }
  }
}
```

### VS Code Extension

1. Install the MCP server (above)
2. Install extension from [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=BurakKTopal.codebase-time-machine)
3. Configure API key (Anthropic, OpenAI, or Gemini)
4. Select code, right-click, "CTM: Why does this code exist?"

## Documentation

- **[MCP Server](ctm_mcp_server/README.md)** - Full tool reference, caching, configuration
- **[VS Code Extension](extensions/vscode/README.md)** - Setup, architecture, token optimization
- **[CLAUDE.md](CLAUDE.md)** - Agent guide for Claude Code users

## License

Both components are licensed under **AGPL-3.0**.

| Component | License |
|-----------|---------|
| MCP Server (`ctm_mcp_server/`) | [AGPL-3.0](ctm_mcp_server/LICENSE) |
| VS Code Extension (`extensions/vscode/`) | [AGPL-3.0](extensions/vscode/LICENSE) |

Copyright 2025 Burak Kucuktopal
