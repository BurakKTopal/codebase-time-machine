# Codebase Time Machine

**Understand why code exists, not just what it does.**

Codebase Time Machine (CTM) is an MCP server for code history analysis. It connects commits, pull requests, issues, and discussions to answer the question: "Why does this code exist?"

## Features

- **35 investigation tools** for tracing code decisions through git history
- **Line-level context**: blame, commits, PRs, linked issues, and discussions in one call
- **SQLite caching** with intelligent TTLs (commits cached forever, PRs/issues for 1 hour)
- **GitHub integration**: works with public repos, or private repos with a token
- **Local git support**: also works with local repositories
- **Code parsing**: extract functions and classes from Python, JavaScript, TypeScript, Go, Rust, C, and C++
- **MCP protocol**: works with Claude Desktop and any MCP-compatible client

## Installation

**From Test PyPI**

```bash
# Option A: pip
pip install -i https://test.pypi.org/simple/ codebase-time-machine

# Option B: pipx (isolated environment)
pipx install -i https://test.pypi.org/simple/ codebase-time-machine

# Verify installation
python -c "import ctm_mcp_server; print('OK')"
```

Package: https://test.pypi.org/project/codebase-time-machine/

**From source (for development)**

```bash
git clone https://github.com/burakktopal/codebase-time-machine.git
cd codebase-time-machine

# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

uv sync
uv run ctm-server
```

## Usage with Claude Desktop

Add to your Claude Desktop config:

**Config location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

**Configuration (PyPI install):**
```json
{
  "mcpServers": {
    "codebase-time-machine": {
      "command": "python",
      "args": [
        "-m",
        "ctm_mcp_server.stdio_server"
      ],
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      }
    }
  }
}
```

**Configuration (from source):**
```json
{
  "mcpServers": {
    "codebase-time-machine": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/codebase-time-machine",
        "run",
        "ctm-server"
      ],
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      }
    }
  }
}
```
The `GITHUB_TOKEN` is optional for public repositories but recommended for higher rate limits. 
**Note**: The Python version Claude Desktop uses must be the same one you used to install codebase-time-machine.

## Tools

CTM provides 35 tools organized by category:

### GitHub Tools

| Tool | Description |
|------|-------------|
| `get_line_context` | Why does this line exist? Blame, commit, PR, issues in one call |
| `get_github_file` | Get file contents |
| `get_github_file_history` | Commits that modified a file |
| `get_github_file_symbols` | Extract functions/classes from a file |
| `get_github_commit` | Get commit details |
| `get_github_commits_batch` | Fetch multiple commits at once |
| `get_github_repo` | Repository information |
| `get_github_branches` | List branches |
| `list_github_tree` | Browse repository file structure |
| `get_pr` | Pull request details with comments and reviews |
| `get_issue` | Issue details with comments |
| `search_prs_for_commit` | Find PRs containing a commit |
| `search_github_code` | Search code in repository |
| `search_github_commits` | Search commit messages |
| `pickaxe_search_github` | Find when code was added/removed |
| `trace_github_symbol_history` | Track function/class evolution across commits |
| `get_code_context` | Full decision chain: file commits, PRs, issues |
| `get_code_owners` | Top contributors for a file |
| `get_change_coupling` | Files that frequently change together |
| `get_activity_summary` | Repository activity overview |
| `get_recent_activity` | Recent commits for file/directory |
| `explain_file` | File overview: purpose, symbols, contributors |
| `explain_directory` | Directory overview and structure |

### Local Git Tools

| Tool | Description |
|------|-------------|
| `get_local_line_context` | Line context with auto GitHub remote detection |
| `get_repo_info` | Repository metadata |
| `list_branches` | List branches with last commit |
| `get_commit` | Commit details |
| `get_commit_diff` | Detailed diff for a commit |
| `trace_file_history` | Complete file change history |
| `get_file_at_commit` | File contents at specific commit |
| `pickaxe_search` | Find when code was added/removed |
| `explain_commit` | Analyze commit intent (bugfix, feature, refactor) |
| `blame_with_context` | Enhanced git blame with PR/issue links |
| `get_file_symbols` | Extract functions/classes from local file |
| `trace_symbol_history` | Track symbol changes in local repo |

## Architecture

```
┌─────────────────────┐     ┌───────────────────┐     ┌──────────────┐
│    MCP Client       │────>│   CTM MCP Server  │────>│  GitHub API  │
│  (Claude Desktop,   │     │     (Python)      │     │  Local Git   │
│   other clients)    │     └─────────┬─────────┘     └──────────────┘
└─────────────────────┘               │
                                      v
                               ┌──────────────┐
                               │ SQLite Cache │
                               │ (~/.ctm/)    │
                               └──────────────┘
```

## Caching

CTM uses SQLite for persistent caching. Cache location: `~/.ctm/cache.db`

**TTL strategy:**
- Commits, git trees: never expire (immutable)
- File contents at specific commits: never expire (immutable)
- Repository metadata: 24 hours
- PRs and issues: 1 hour
- Search results: 30 minutes

Override cache location with `CTM_CACHE_PATH` environment variable.

## Agent Guide (CLAUDE.md)

The repository includes [CLAUDE.md](CLAUDE.md), an agent guide that teaches LLMs how to use CTM tools effectively. It covers:

- Speed hierarchy (which tools are fast vs slow)
- Tool selection for different questions
- Caching strategies and batch operations
- Response templates and investigation patterns

To use it: copy CLAUDE.md to your project root. Claude Code and similar tools will read it automatically and use CTM tools more effectively.

## VS Code Extension

An optional VS Code extension is available in `extensions/vscode/`. It adds a right-click menu option "Why does this code exist?" that runs CTM analysis on selected code.

See [extensions/vscode/README.md](extensions/vscode/README.md) for setup instructions.

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the full development guide.

**Quick commands:**

```bash
uv sync --all-extras      # Install dev dependencies
uv run ruff check ctm_mcp_server --fix  # Lint
uv run ruff format ctm_mcp_server       # Format
uv run pytest             # Test
```

## License

AGPL-3.0. See [LICENSE](LICENSE) for details.

Copyright 2025 Burak Kucuktopal
