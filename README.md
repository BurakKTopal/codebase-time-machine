# Codebase Time Machine

**Understand why code exists, not just what it does.**

Codebase Time Machine (CTM) is an LLM-agnostic tool server for code history analysis. It helps developers quickly answer the question: *"Why does this code exist?"* by connecting the dots between commits, pull requests, issues, and discussions.

## Features

- **Line-level context**: Get the full story behind any line of code - blame, PRs, linked issues, discussions
- **Smart caching**: SQLite-based caching for fast, repeated queries
- **GitHub integration**: Works with any GitHub repository (public or private with token)
- **Local git support**: Also works with local repositories without GitHub
- **Code parsing**: Extract symbols (functions, classes) from Python, JavaScript, TypeScript, Go, Rust, C, C++
- **VSCode Extension**: Select code and ask "Why does this exist?" directly in your editor

## Quick Start

### Installation

**Recommended: PyPI Installation**

For end users, install via pip or pipx (no uv required):

```bash
# Option A: pip (simplest)
pip install codebase-time-machine

# Option B: pipx (isolated installation)
pipx install codebase-time-machine

# Verify installation
ctm-server --version
```

**Alternative: Local Development**

For contributors and development:

```bash
# Clone the repository
git clone https://github.com/burakktopal/codebase-time-machine.git
cd codebase-time-machine

# Install uv if you don't have it
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows:
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Install dependencies
uv sync

# Run server
uv run ctm-server
```

### Set up GitHub token (optional, for private repos)

```bash
export GITHUB_TOKEN=your_token_here
```

### Usage with Claude Desktop

After installation via pip/pipx, configure Claude Desktop:

**Config location**:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

**Configuration**:
```json
{
  "mcpServers": {
    "codebase-time-machine": {
      "command": "ctm-server",
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

**For local development** (if using cloned repo):
```json
{
  "mcpServers": {
    "codebase-time-machine": {
      "command": "uv",
      "args": ["run", "ctm-server"],
      "cwd": "/absolute/path/to/codebase-time-machine",
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

Restart Claude Desktop after updating the config.

### VSCode Extension

The VS Code extension automatically detects your installation method:
- **pip/pipx install** → Runs `ctm-server` directly
- **uv tool install** → Runs `uv tool run ctm-server`
- **Local repo** → Runs `uv run ctm-server` in repo directory

**Setup**:
1. Install the extension from the `extensions/vscode` folder
2. Configure your AI provider settings (Anthropic, OpenAI, or Gemini)
3. Select code in your editor
4. Run command: "CTM: Why Does This Code Exist?"

## How It Works

CTM uses the Model Context Protocol (MCP) to expose 30+ tools for investigating code history:

| Tool | Speed | Use Case |
|------|-------|----------|
| `get_line_context` | Fast | Why does this line exist? (primary tool) |
| `get_github_file_history` | Fast | What changed in this file? |
| `explain_file` | Fast | File overview and contributors |
| `trace_github_symbol_history` | Medium | How did this function evolve? |
| `get_code_context` | Slow | Full decision chain for a file |

## Architecture

```
┌─────────────────┐     ┌───────────────┐     ┌──────────────┐
│ VSCode Extension│────>│   MCP Server  │────>│ GitHub API   │
│   (TypeScript)  │     │   (Python)    │     │ Local Git    │
└─────────────────┘     └───────────────┘     └──────────────┘
                              │
                              v
                        ┌──────────┐
                        │  Cache   │
                        │ (SQLite) │
                        └──────────┘
```

## Documentation

For detailed usage and tool reference, see [CLAUDE.md](CLAUDE.md).

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run linter
uv run ruff check ctm_mcp_server --fix

# Run formatter
uv run ruff format ctm_mcp_server

# Run tests
uv run pytest
```

## License

AGPL-3.0 - See [LICENSE](LICENSE) for details.

Copyright (C) 2024 Burak Kucuktopal
