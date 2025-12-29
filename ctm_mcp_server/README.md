# CTM MCP Server

The MCP (Model Context Protocol) server that powers Codebase Time Machine. Use this with Claude Code, Claude Desktop, or any MCP-compatible client.

## Quick Start

### Option A: Install from PyPI (Recommended for Users)

```bash
pip install codebase-time-machine

# Or with pipx (isolated environment)
pipx install codebase-time-machine
```

**Claude Code config** - create a `.mcp.json` file in your project root:
```json
{
  "mcpServers": {
    "ctm": {
      "command": "python",
      "args": ["-m", "ctm_mcp_server.stdio_server"],
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      }
    }
  }
}
```

Then restart Claude Code. It will automatically detect and use the MCP server.

### Option B: Run from Source (For Development)

```bash
git clone https://github.com/BurakKTopal/codebase-time-machine.git
cd codebase-time-machine
uv sync
```

The repo includes a `.mcp.json` that configures Claude Code automatically:
```json
{
  "mcpServers": {
    "ctm": {
      "command": "uv",
      "args": ["run", "ctm_server.py"]
    }
  }
}
```

Just open the project in Claude Code and the MCP server is available.

## Claude Desktop Setup

Add to your Claude Desktop config:

**Config locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

**If installed via pip:**
```json
{
  "mcpServers": {
    "ctm": {
      "command": "python",
      "args": ["-m", "ctm_mcp_server.stdio_server"],
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      }
    }
  }
}
```

**If running from source:**
```json
{
  "mcpServers": {
    "ctm": {
      "command": "uv",
      "args": ["--directory", "/path/to/codebase-time-machine", "run", "ctm_server.py"],
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      }
    }
  }
}
```

## GitHub Token (Optional)

The `GITHUB_TOKEN` is optional for public repositories but recommended for:
- Private repository access
- Higher API rate limits (5000/hour vs 60/hour)

Get one at: https://github.com/settings/tokens (needs `repo` scope for private repos)

## Tools Reference

CTM provides 32 tools for code investigation:

### Primary Tools (Start Here)

| Tool | Speed | Description |
|------|-------|-------------|
| `get_line_context` | 2-4s | **Flagship tool** - Why does this line exist? Returns blame, commit, PR, issues, discussions |
| `get_local_line_context` | 2-4s | Same as above, for local repos (auto-bridges to GitHub if remote exists) |
| `get_github_file` | <1s | Get file contents |
| `explain_file` | 3-5s | File overview: purpose, symbols, contributors, recent changes |

### GitHub Tools

| Tool | Description |
|------|-------------|
| `get_github_file_history` | Commits that modified a file |
| `get_github_file_symbols` | Extract functions/classes from a file |
| `get_github_commit` | Get commit details |
| `get_github_commits_batch` | Fetch multiple commits at once (faster) |
| `get_github_repo` | Repository information |
| `get_github_branches` | List branches |
| `list_github_tree` | Browse repository file structure |
| `get_pr` | Pull request details with comments and reviews |
| `get_issue` | Issue details with comments |
| `search_prs_for_commit` | Find PRs containing a commit |
| `search_github_code` | Search code in repository |
| `search_github_commits` | Search commit messages |
| `pickaxe_search_github` | Find when code was added/removed |
| `trace_github_symbol_history` | Track function/class evolution |
| `get_code_owners` | Top contributors for a file |
| `get_change_coupling` | Files that frequently change together |
| `get_activity_summary` | Repository/path activity overview |

### Local Git Tools

| Tool | Description |
|------|-------------|
| `get_repo_info` | Repository metadata |
| `list_branches` | List branches with last commit |
| `get_commit` | Commit details |
| `get_commit_diff` | Detailed diff for a commit |
| `trace_file_history` | Complete file change history |
| `get_file_at_commit` | File contents at specific commit |
| `pickaxe_search` | Find when code was added/removed |
| `explain_commit` | Analyze commit intent (bugfix, feature, refactor) |
| `blame_with_context` | Git blame with commit metadata |
| `get_file_symbols` | Extract functions/classes from local file |
| `trace_symbol_history` | Track symbol changes in local repo |

---

## Design Philosophy

### Powerful Flagship Tools

Instead of simple wrappers around git commands, CTM tools are designed to **aggregate multiple data sources in a single call**:

**`get_line_context` / `get_local_line_context`** - The flagship tool that:
- Runs git blame to find who last modified the code
- Automatically runs **per-line pickaxe search** to find the true origin of each line (when code was first introduced)
- Groups origins by commit SHA for efficient multi-line selections
- Detects if code was introduced as a comment vs active code
- Fetches the associated PR (if the commit came from a PR)
- Extracts linked issues from PR/commit messages
- **Detects patterns** (commented code with active alternatives, TODOs, stale fixes)
- **Provides quick answers** when patterns are clear (e.g., "This is unused alternative code")
- **Shows nearby context** to detect active implementations below commented code
- **Calculates confidence scores** with specific signals for investigation quality
- Returns everything in one structured response with `code_sections` containing grouped origins

**This is the difference between "a git wrapper" and "a code investigation tool".**

### Intelligent Caching

CTM recognizes that git data has different mutability characteristics:

| Data Type | TTL | Reason |
|-----------|-----|--------|
| Commits | Forever | Commits are immutable |
| File contents at commit | Forever | Immutable (content-addressed) |
| Git trees | Forever | Immutable |
| Repository metadata | 24 hours | Rarely changes |
| PRs and issues | 1 hour | May get new comments |
| Search results | 30 minutes | Index updates |

**Result**: Repeat investigations are nearly instant, and GitHub API rate limits are preserved.

### Batch Operations

Tools like `get_github_commits_batch` fetch multiple items in parallel:
- First call: 5 commits → 5 API calls (cached)
- Second call: Same 5 commits → 0 API calls (cache hits)
- Mixed call: 3 cached + 2 new → 2 API calls

This makes follow-up investigations significantly faster.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | (none) | GitHub personal access token |
| `CTM_CACHE_PATH` | `~/.ctm/cache.db` | SQLite cache location |

### Caching

CTM uses SQLite for persistent caching at `~/.ctm/cache.db`.

**TTL strategy:**
- Commits, git trees: never expire (immutable)
- File contents at specific commits: never expire (immutable)
- Repository metadata: 24 hours
- PRs and issues: 1 hour
- Search results: 30 minutes

## Agent Guide

For optimal tool usage, add [CLAUDE.md](../CLAUDE.md) to your project. It teaches LLMs:
- Which tools are fast vs slow
- Tool selection for different questions
- Caching strategies and batch operations

## Troubleshooting

### "Module not found"
```bash
python -c "import ctm_mcp_server; print('OK')"
```

### "Rate limit exceeded"
Add a `GITHUB_TOKEN` for 5000 requests/hour instead of 60.

### "Repository not found"
For private repos, ensure your token has `repo` scope.

## License

AGPL-3.0
