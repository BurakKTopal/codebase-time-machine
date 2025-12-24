# Codebase Time Machine - VS Code Extension

Understand why code exists, not just what it does.

## Features

- **Right-click any code** and select "CTM: Why does this code exist?"
- Get instant AI-powered explanations including:
  - Why the code was written
  - Commit context
  - Pull Request discussions
  - Related issues
  - Technical debt warnings

## Prerequisites

1. **Python 3.11+** with `uv` package manager installed
2. **Codebase Time Machine** MCP server installed:
   ```bash
   cd /path/to/CodebaseTimeMachine
   uv sync
   ```
3. **Anthropic API Key** (optional but recommended for AI summaries)
   - Get one at: https://console.anthropic.com/

## Setup

1. Install the extension
2. Configure your Anthropic API key:
   - Open Settings (Ctrl+,)
   - Search for "CTM: Anthropic API Key"
   - Paste your API key

## Usage

1. Open a file in a GitHub repository
2. Select 1-5 lines of code
3. Right-click → "CTM: Why does this code exist?"
4. View results in the side panel

## Settings

- `ctm.anthropicApiKey`: Your Anthropic API key for AI summaries
- `ctm.serverCommand`: Command to start CTM server (default: "uv")
- `ctm.serverArgs`: Arguments for server command (default: ["run", "ctm-server"])

## Troubleshooting

**"Failed to start CTM server"**
- Make sure `uv` is installed: `uv --version`
- Make sure CTM is installed: `uv sync` in the CTM directory

**"Cannot detect GitHub repo"**
- The extension only works with GitHub repositories
- Make sure your repo has a GitHub remote: `git remote -v`

**"No AI summary, just raw context"**
- Add your Anthropic API key in settings
- The extension works without an API key but shows raw context only

## License

MIT
