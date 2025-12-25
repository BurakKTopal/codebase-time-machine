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

```bash
# Install with uv (recommended)
uv pip install codebase-time-machine

# Or clone and install
git clone https://github.com/burak/codebase-time-machine
cd codebase-time-machine
uv sync
```

### Set up GitHub token (optional, for private repos)

```bash
export GITHUB_TOKEN=your_token_here
```

### Run the MCP Server

```bash
# Start the MCP server
ctm-server
```

### VSCode Extension

1. Install the extension from the `extensions/vscode` folder
2. Configure your Anthropic API key in VSCode settings (`ctm.anthropicApiKey`)
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

MIT
