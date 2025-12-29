"""
Codebase Time Machine - MCP Protocol Server

This module implements the MCP (Model Context Protocol) server using stdio transport.
It exposes all CTM tools to LLM clients like Claude.
"""

import json
import os
import re
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ctm_mcp_server.data.cache import get_cache
from ctm_mcp_server.data.git_repo import GitRepo, GitRepoError
from ctm_mcp_server.data.github_client import GitHubClient, GitHubClientError
from ctm_mcp_server.models.github_models import Comment
from ctm_mcp_server.models.result_models import IntentType
from ctm_mcp_server.parsing.parser import CodeParser, ParserError

# Create the MCP server instance
server = Server("codebase-time-machine")

# Initialize global cache for GitHub API responses
# Allow override via environment variable, otherwise use user home directory
cache_path = os.environ.get("CTM_CACHE_PATH")
if cache_path:
    db_path = cache_path
else:
    cache_dir = Path.home() / ".ctm"
    cache_dir.mkdir(exist_ok=True)
    db_path = str(cache_dir / "cache.db")

_cache = get_cache(db_path=db_path)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available CTM tools.

    This function returns the schema for all tools that can be called
    by the LLM client.
    """
    return [
        Tool(
            name="get_repo_info",
            description="Get basic information about a git repository including name, branches, recent commits, and contributors.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="list_branches",
            description="List all branches in a git repository with their last commit dates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "include_remote": {
                        "type": "boolean",
                        "description": "Include remote-tracking branches (default: false)",
                        "default": False,
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="get_commit",
            description="Get details of a specific commit including message, author, timestamp, and files changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "sha": {
                        "type": "string",
                        "description": "The commit SHA (full or abbreviated)",
                    },
                },
                "required": ["repo_path", "sha"],
            },
        ),
        Tool(
            name="get_commit_diff",
            description="Get the detailed diff for a specific commit, showing what changed in each file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "sha": {
                        "type": "string",
                        "description": "The commit SHA",
                    },
                },
                "required": ["repo_path", "sha"],
            },
        ),
        Tool(
            name="trace_file_history",
            description="Get the complete history of changes to a specific file, showing all commits that modified it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (relative to repo root)",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum number of commits to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["repo_path", "file_path"],
            },
        ),
        Tool(
            name="get_file_at_commit",
            description="Get the contents of a file at a specific commit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "sha": {
                        "type": "string",
                        "description": "The commit SHA",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (relative to repo root)",
                    },
                },
                "required": ["repo_path", "sha", "file_path"],
            },
        ),
        Tool(
            name="pickaxe_search",
            description="Find commits that introduced or removed a specific piece of code. Uses git's pickaxe feature (-S) to find when code was first added or last removed. This is the best way to find when a piece of code was originally introduced to the codebase.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "search_string": {
                        "type": "string",
                        "description": "The code/string to search for. Can be a function name, variable, or any text that was added/removed.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional: limit search to a specific file (relative to repo root)",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum number of commits to return (default: 20)",
                        "default": 20,
                    },
                    "regex": {
                        "type": "boolean",
                        "description": "If true, treat search_string as a regex pattern (default: false)",
                        "default": False,
                    },
                    "follow_renames": {
                        "type": "boolean",
                        "description": "If true (default), follow file renames to find the true origin of code even if the file was renamed after the code was added.",
                        "default": True,
                    },
                },
                "required": ["repo_path", "search_string"],
            },
        ),
        Tool(
            name="pickaxe_search_github",
            description="Find commits that introduced or removed a specific piece of code via GitHub API. Slower than local pickaxe_search but works for remote repos without cloning. Analyzes commit diffs to find when code appeared/disappeared.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner (username or organization)",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "search_string": {
                        "type": "string",
                        "description": "The code/string to search for in commit diffs",
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional: limit search to a specific file path",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum number of commits to analyze (default: 20)",
                        "default": 20,
                    },
                    "regex": {
                        "type": "boolean",
                        "description": "If true, treat search_string as a regex pattern (default: false)",
                        "default": False,
                    },
                    "follow_renames": {
                        "type": "boolean",
                        "description": "If true (default), follow file renames to find the true origin of code even if the file was renamed.",
                        "default": True,
                    },
                },
                "required": ["owner", "repo", "search_string"],
            },
        ),
        Tool(
            name="explain_commit",
            description="Analyze a commit and explain its intent, categorizing it as bugfix, feature, refactor, etc. with confidence score.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "sha": {
                        "type": "string",
                        "description": "The commit SHA to analyze",
                    },
                },
                "required": ["repo_path", "sha"],
            },
        ),
        Tool(
            name="blame_with_context",
            description="Git blame with commit metadata. Shows who changed each line with commit details and extracts PR/issue references from commit messages. For full PR/issue context, use get_local_line_context instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (relative to repo root)",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start line number (1-indexed, optional)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line number (1-indexed, optional)",
                    },
                },
                "required": ["repo_path", "file_path"],
            },
        ),
        Tool(
            name="get_local_line_context",
            description="Get line context for local repo with GitHub remote bridging. If the local repo has a GitHub remote, provides full PR/issue context like get_line_context. Otherwise falls back to basic blame. This is the flagship tool for local repos.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (relative to repo root)",
                    },
                    "line_start": {
                        "type": "integer",
                        "description": "Starting line number (1-indexed)",
                    },
                    "line_end": {
                        "type": "integer",
                        "description": "Ending line number (default: same as line_start)",
                    },
                    "include_discussions": {
                        "type": "boolean",
                        "description": "Fetch PR/issue comments for richer context (slower but more complete, default: true)",
                    },
                    "history_depth": {
                        "type": "integer",
                        "description": "Number of historical commits to analyze (default: 1). Use 5-10 to find when code was originally added.",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Git ref (branch, tag, or SHA) to analyze. Defaults to HEAD (current branch).",
                    },
                    "include_nearby_context": {
                        "type": "boolean",
                        "description": "Check lines before/after selection for related code (e.g., active alternatives to commented code). Default: true.",
                        "default": True,
                    },
                },
                "required": ["repo_path", "file_path", "line_start"],
            },
        ),
        # GitHub API Tools - Work on ANY public repo without cloning
        Tool(
            name="get_github_repo",
            description="Get information about any GitHub repository without cloning. Works with any public repo.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner (username or organization)",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                },
                "required": ["owner", "repo"],
            },
        ),
        Tool(
            name="get_github_branches",
            description="List branches of any GitHub repository without cloning.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                },
                "required": ["owner", "repo"],
            },
        ),
        Tool(
            name="get_github_commit",
            description="Get details of a specific commit from any GitHub repository without cloning.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "sha": {
                        "type": "string",
                        "description": "Commit SHA",
                    },
                },
                "required": ["owner", "repo", "sha"],
            },
        ),
        Tool(
            name="get_github_commits_batch",
            description="Get details of multiple commits at once from any GitHub repository. Much more efficient than calling get_github_commit multiple times. Fetches missing commits in parallel and uses caching.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "shas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of commit SHAs to fetch",
                    },
                },
                "required": ["owner", "repo", "shas"],
            },
        ),
        Tool(
            name="get_github_file_history",
            description="Get the commit history for a specific file from any GitHub repository without cloning.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum commits to return (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["owner", "repo", "path"],
            },
        ),
        Tool(
            name="get_github_file",
            description="Get the contents of a file from any GitHub repository at a specific ref (branch/tag/SHA) without cloning.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Git ref (branch, tag, or SHA). Defaults to default branch.",
                    },
                    "max_size": {
                        "type": "integer",
                        "description": "Maximum content size in bytes before truncation (default: 50000 = 50KB, use 0 for no limit)",
                        "default": 50000,
                    },
                },
                "required": ["owner", "repo", "path"],
            },
        ),
        Tool(
            name="get_pr",
            description="Get detailed information about a GitHub Pull Request including comments, reviews, and linked issues.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "pr_number": {
                        "type": "integer",
                        "description": "Pull request number",
                    },
                },
                "required": ["owner", "repo", "pr_number"],
            },
        ),
        Tool(
            name="get_issue",
            description="Get detailed information about a GitHub Issue including comments.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "issue_number": {
                        "type": "integer",
                        "description": "Issue number",
                    },
                },
                "required": ["owner", "repo", "issue_number"],
            },
        ),
        Tool(
            name="search_prs_for_commit",
            description="Find pull requests that include a specific commit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "sha": {
                        "type": "string",
                        "description": "Commit SHA to search for",
                    },
                },
                "required": ["owner", "repo", "sha"],
            },
        ),
        # Search tools
        Tool(
            name="search_github_code",
            description="Search for code in any GitHub repository. Supports GitHub code search syntax (e.g., 'function language:python', 'import requests extension:py').",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (supports GitHub code search syntax: language:, extension:, path:, filename:)",
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (max 100, default 30)",
                        "default": 30,
                    },
                },
                "required": ["owner", "repo", "query"],
            },
        ),
        Tool(
            name="search_github_commits",
            description="Search for commits in any GitHub repository. Supports GitHub commit search syntax (e.g., 'fix bug', 'author:username', 'committer-date:>2023-01-01').",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (supports: author:, committer:, committer-date:, author-date:, merge:, hash:)",
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (max 100, default 30)",
                        "default": 30,
                    },
                },
                "required": ["owner", "repo", "query"],
            },
        ),
        # Symbol tracking tools
        Tool(
            name="get_file_symbols",
            description="Extract code symbols (functions, classes, methods) from a local file using tree-sitter parsing. Supports Python, JavaScript, TypeScript, Go, and Rust.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the source file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_github_file_symbols",
            description="Extract code symbols from a file in any GitHub repository without cloning. Supports Python, JavaScript, TypeScript, Go, and Rust.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Git ref (branch, tag, or SHA). Defaults to default branch.",
                    },
                },
                "required": ["owner", "repo", "path"],
            },
        ),
        Tool(
            name="trace_symbol_history",
            description="Track the history of a specific symbol (function/class/method) across commits in a LOCAL repository. Shows when it was added, modified, or renamed. Supports Python, JavaScript, TypeScript, Go, and Rust.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (relative to repo root)",
                    },
                    "symbol_name": {
                        "type": "string",
                        "description": "Name of the symbol to track (e.g., 'my_function' or 'MyClass.my_method')",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum commits to analyze (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["repo_path", "file_path", "symbol_name"],
            },
        ),
        Tool(
            name="trace_github_symbol_history",
            description="Track the history of a specific symbol (function/class/method) across commits in any GitHub repository WITHOUT cloning. Shows when it was added, modified, or deleted with commit details. Supports Python, JavaScript, TypeScript, Go, and Rust.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root",
                    },
                    "symbol_name": {
                        "type": "string",
                        "description": "Name of the symbol to track (e.g., 'my_function' or 'MyClass.my_method')",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum commits to analyze (default: 20, max: 50 to limit API calls)",
                        "default": 20,
                    },
                },
                "required": ["owner", "repo", "path", "symbol_name"],
            },
        ),
        # Analysis tools - Phase C
        Tool(
            name="get_code_owners",
            description="Find who knows this code best by analyzing commit history. Returns contributors ranked by number of commits, lines changed, and recency.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory path relative to repo root",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum commits to analyze (default: 100)",
                        "default": 100,
                    },
                },
                "required": ["owner", "repo", "path"],
            },
        ),
        Tool(
            name="get_change_coupling",
            description="Find files that frequently change together with the target file. Reveals hidden dependencies and architectural relationships.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path to analyze",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum commits to analyze (default: 50)",
                        "default": 50,
                    },
                    "min_coupling": {
                        "type": "number",
                        "description": "Minimum coupling ratio (0-1) to include (default: 0.3)",
                        "default": 0.3,
                    },
                },
                "required": ["owner", "repo", "path"],
            },
        ),
        Tool(
            name="get_activity_summary",
            description="Get aggregated summary of repository activity: commits by type (bugfix/feature/etc), top contributors, most changed files. Can filter by time range and path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 30)",
                        "default": 30,
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional: filter to specific file or directory path",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum commits to analyze (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["owner", "repo"],
            },
        ),
        # Explanation & Onboarding tools - Phase D
        Tool(
            name="explain_file",
            description="Get a comprehensive overview of a file: what it does, key symbols, recent changes, top contributors, and why it exists. Great for onboarding.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root",
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Include file content preview (default: false)",
                        "default": False,
                    },
                },
                "required": ["owner", "repo", "path"],
            },
        ),
        Tool(
            name="list_github_tree",
            description="Get the complete file tree of a GitHub repository in one fast API call. Essential for understanding codebase structure. Can filter by path prefix and file extension. Optionally includes activity info (contributors, recent commits).",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "path_prefix": {
                        "type": "string",
                        "description": "Filter to paths starting with this prefix (e.g., 'src/', 'tests/')",
                    },
                    "extension": {
                        "type": "string",
                        "description": "Filter to files with this extension (e.g., '.py', '.ts')",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum directory depth to include (default: unlimited)",
                    },
                    "include_activity": {
                        "type": "boolean",
                        "description": "Include recent activity info: commits, contributors, key files (default: false)",
                        "default": False,
                    },
                },
                "required": ["owner", "repo"],
            },
        ),
        Tool(
            name="get_line_context",
            description="Gather all context about why specific lines of code exist. Aggregates: blame → commit → PR → issues → discussions. Returns structured data for LLM reasoning. This is the flagship tool for answering 'Why does this code exist?'",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file relative to repo root",
                    },
                    "line_start": {
                        "type": "integer",
                        "description": "Starting line number (1-indexed)",
                    },
                    "line_end": {
                        "type": "integer",
                        "description": "Ending line number (default: same as line_start)",
                    },
                    "include_discussions": {
                        "type": "boolean",
                        "description": "Fetch PR/issue comments for richer context (slower but more complete)",
                        "default": True,
                    },
                    "history_depth": {
                        "type": "integer",
                        "description": "Number of historical commits to analyze (default: 1 for just blame, 5-10 recommended for finding when code was introduced)",
                        "default": 1,
                    },
                    "ref": {
                        "type": "string",
                        "description": "Git ref (branch, tag, or SHA) to analyze. Defaults to the repository's default branch (usually main or master).",
                    },
                },
                "required": ["owner", "repo", "file_path", "line_start"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls from the LLM client.

    This function routes tool calls to the appropriate implementation
    and returns the results as TextContent.
    """
    try:
        if name == "get_repo_info":
            result = await _get_repo_info(arguments["repo_path"])
        elif name == "list_branches":
            result = await _list_branches(
                arguments["repo_path"],
                arguments.get("include_remote", False),
            )
        elif name == "get_commit":
            result = await _get_commit(arguments["repo_path"], arguments["sha"])
        elif name == "get_commit_diff":
            result = await _get_commit_diff(arguments["repo_path"], arguments["sha"])
        elif name == "trace_file_history":
            result = await _trace_file_history(
                arguments["repo_path"],
                arguments["file_path"],
                arguments.get("max_commits", 50),
            )
        elif name == "get_file_at_commit":
            result = await _get_file_at_commit(
                arguments["repo_path"],
                arguments["sha"],
                arguments["file_path"],
            )
        elif name == "pickaxe_search":
            result = await _pickaxe_search(
                arguments["repo_path"],
                arguments["search_string"],
                arguments.get("file_path"),
                arguments.get("max_commits", 20),
                arguments.get("regex", False),
                arguments.get("follow_renames", True),
            )
        elif name == "pickaxe_search_github":
            result = await _pickaxe_search_github(
                arguments["owner"],
                arguments["repo"],
                arguments["search_string"],
                arguments.get("path"),
                arguments.get("max_commits", 20),
                arguments.get("regex", False),
                arguments.get("follow_renames", True),
            )
        elif name == "explain_commit":
            result = await _explain_commit(arguments["repo_path"], arguments["sha"])
        elif name == "blame_with_context":
            result = await _blame_with_context(
                arguments["repo_path"],
                arguments["file_path"],
                arguments.get("start_line"),
                arguments.get("end_line"),
            )
        elif name == "get_local_line_context":
            result = await _get_local_line_context(
                arguments["repo_path"],
                arguments["file_path"],
                arguments["line_start"],
                arguments.get("line_end"),
                arguments.get("include_discussions", True),
                arguments.get("history_depth", 1),
                arguments.get("ref"),  # Branch/tag/SHA to analyze
                arguments.get("include_nearby_context", True),  # Check nearby code
            )
        # GitHub API tools
        elif name == "get_github_repo":
            result = await _get_github_repo(arguments["owner"], arguments["repo"])
        elif name == "get_github_branches":
            result = await _get_github_branches(arguments["owner"], arguments["repo"])
        elif name == "get_github_commit":
            result = await _get_github_commit(
                arguments["owner"], arguments["repo"], arguments["sha"]
            )
        elif name == "get_github_commits_batch":
            result = await _get_github_commits_batch(
                arguments["owner"], arguments["repo"], arguments["shas"]
            )
        elif name == "get_github_file_history":
            result = await _get_github_file_history(
                arguments["owner"],
                arguments["repo"],
                arguments["path"],
                arguments.get("max_commits", 30),
            )
        elif name == "get_github_file":
            result = await _get_github_file(
                arguments["owner"],
                arguments["repo"],
                arguments["path"],
                arguments.get("ref"),
                arguments.get("max_size", 50000),
            )
        elif name == "get_pr":
            result = await _get_pr(arguments["owner"], arguments["repo"], arguments["pr_number"])
        elif name == "get_issue":
            result = await _get_issue(
                arguments["owner"], arguments["repo"], arguments["issue_number"]
            )
        elif name == "search_prs_for_commit":
            result = await _search_prs_for_commit(
                arguments["owner"], arguments["repo"], arguments["sha"]
            )
        # Search tools
        elif name == "search_github_code":
            result = await _search_github_code(
                arguments["owner"],
                arguments["repo"],
                arguments["query"],
                arguments.get("per_page", 30),
            )
        elif name == "search_github_commits":
            result = await _search_github_commits(
                arguments["owner"],
                arguments["repo"],
                arguments["query"],
                arguments.get("per_page", 30),
            )
        # Symbol tracking tools
        elif name == "get_file_symbols":
            result = await _get_file_symbols(arguments["file_path"])
        elif name == "get_github_file_symbols":
            result = await _get_github_file_symbols(
                arguments["owner"],
                arguments["repo"],
                arguments["path"],
                arguments.get("ref"),
            )
        elif name == "trace_symbol_history":
            result = await _trace_symbol_history(
                arguments["repo_path"],
                arguments["file_path"],
                arguments["symbol_name"],
                arguments.get("max_commits", 30),
            )
        elif name == "trace_github_symbol_history":
            result = await _trace_github_symbol_history(
                arguments["owner"],
                arguments["repo"],
                arguments["path"],
                arguments["symbol_name"],
                min(arguments.get("max_commits", 20), 50),  # Cap at 50 to limit API calls
            )
        # Analysis tools
        elif name == "get_code_owners":
            result = await _get_code_owners(
                arguments["owner"],
                arguments["repo"],
                arguments["path"],
                arguments.get("max_commits", 100),
            )
        elif name == "get_change_coupling":
            result = await _get_change_coupling(
                arguments["owner"],
                arguments["repo"],
                arguments["path"],
                arguments.get("max_commits", 50),
                arguments.get("min_coupling", 0.3),
            )
        elif name == "get_activity_summary":
            result = await _get_activity_summary(
                arguments["owner"],
                arguments["repo"],
                arguments.get("days", 30),
                arguments.get("path"),
                arguments.get("max_commits", 50),
            )
        # Explanation & Onboarding tools
        elif name == "explain_file":
            result = await _explain_file(
                arguments["owner"],
                arguments["repo"],
                arguments["path"],
                arguments.get("include_content", False),
            )
        elif name == "list_github_tree":
            result = await _list_github_tree(
                arguments["owner"],
                arguments["repo"],
                arguments.get("path_prefix"),
                arguments.get("extension"),
                arguments.get("max_depth"),
                arguments.get("include_activity", False),
            )
        elif name == "get_line_context":
            result = await _get_line_context(
                arguments["owner"],
                arguments["repo"],
                arguments["file_path"],
                arguments["line_start"],
                arguments.get("line_end"),
                arguments.get("include_discussions", True),
                arguments.get("history_depth", 1),
                arguments.get("ref"),  # Branch/tag/SHA to analyze
            )
        else:
            result = {"success": False, "error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except GitRepoError as e:
        error_result = {"success": False, "error": str(e)}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]
    except GitHubClientError as e:
        error_result = {"success": False, "error": f"GitHub API error: {e}"}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]
    except ParserError as e:
        error_result = {"success": False, "error": f"Parser error: {e}"}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]
    except Exception as e:
        error_result = {"success": False, "error": f"Unexpected error: {e}"}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


# Tool implementations using GitRepo
async def _get_repo_info(repo_path: str) -> dict[str, Any]:
    """Get repository information."""
    repo = GitRepo(repo_path)

    # Get last commit info
    last_commit = None
    try:
        branches = repo.get_branches()
        if branches:
            for branch in branches:
                if branch.is_current and branch.last_commit_sha:
                    last_commit = repo.get_commit(branch.last_commit_sha)
                    break
    except GitRepoError:
        pass

    return {
        "success": True,
        "name": repo.name,
        "path": str(repo.path),
        "default_branch": repo.default_branch,
        "current_branch": repo.current_branch,
        "is_bare": repo.is_bare,
        "is_dirty": repo.is_dirty,
        "branches_count": len(repo.get_branches()),
        "remotes": repo.get_remotes(),
        "contributors": repo.get_contributors(max_count=10),
        "last_commit": (
            {
                "sha": last_commit.short_sha,
                "message": last_commit.subject,
                "author": str(last_commit.author),
                "date": last_commit.committed_date.isoformat(),
            }
            if last_commit
            else None
        ),
    }


async def _list_branches(repo_path: str, include_remote: bool = False) -> dict[str, Any]:
    """List all branches."""
    repo = GitRepo(repo_path)
    branches = repo.get_branches(include_remote=include_remote)

    return {
        "success": True,
        "current_branch": repo.current_branch,
        "branches": [
            {
                "name": b.name,
                "is_current": b.is_current,
                "is_remote": b.is_remote,
                "last_commit_sha": b.last_commit_sha,
                "last_commit_date": b.last_commit_date.isoformat() if b.last_commit_date else None,
                "last_commit_message": b.last_commit_message,
            }
            for b in branches
        ],
    }


async def _get_commit(repo_path: str, sha: str) -> dict[str, Any]:
    """Get commit details."""
    from ctm_mcp_server.utils import detect_github_remote

    repo = GitRepo(repo_path)
    commit = repo.get_commit(sha)

    # Detect GitHub remote for constructing commit URL
    github_info = detect_github_remote(repo)
    html_url = None
    pr_url = None
    if github_info:
        owner, repo_name = github_info
        html_url = f"https://github.com/{owner}/{repo_name}/commit/{commit.sha}"
        if commit.pr_number:
            pr_url = f"https://github.com/{owner}/{repo_name}/pull/{commit.pr_number}"

    return {
        "success": True,
        "commit": {
            "sha": commit.sha,
            "short_sha": commit.short_sha,
            "message": commit.message,
            "subject": commit.subject,
            "author": {"name": commit.author.name, "email": commit.author.email},
            "committer": {"name": commit.committer.name, "email": commit.committer.email},
            "authored_date": commit.authored_date.isoformat(),
            "committed_date": commit.committed_date.isoformat(),
            "parents": commit.parents,
            "is_merge_commit": commit.is_merge_commit,
            "files_changed": [
                {
                    "path": f.path,
                    "old_path": f.old_path,
                    "change_type": f.change_type,
                }
                for f in commit.files_changed
            ],
            "pr_number": commit.pr_number,
            "issue_numbers": commit.issue_numbers,
            "html_url": html_url,
            "pr_url": pr_url,
        },
    }


async def _get_commit_diff(repo_path: str, sha: str) -> dict[str, Any]:
    """Get commit diff."""
    repo = GitRepo(repo_path)
    diff_files = repo.get_diff(sha)

    return {
        "success": True,
        "sha": sha,
        "files": [
            {
                "path": f.path,
                "old_path": f.old_path,
                "change_type": f.change_type,
                "is_binary": f.is_binary,
                "additions": f.additions,
                "deletions": f.deletions,
                "hunks": [
                    {
                        "header": h.header,
                        "old_start": h.old_start,
                        "old_count": h.old_count,
                        "new_start": h.new_start,
                        "new_count": h.new_count,
                        "lines": h.lines[:50],  # Limit lines to prevent huge output
                    }
                    for h in f.hunks
                ],
            }
            for f in diff_files
        ],
    }


async def _trace_file_history(repo_path: str, file_path: str, max_commits: int) -> dict[str, Any]:
    """Trace file history."""
    repo = GitRepo(repo_path)
    commits = repo.get_file_history(file_path, max_commits=max_commits)

    return {
        "success": True,
        "file_path": file_path,
        "total_commits": len(commits),
        "commits": [
            {
                "sha": c.short_sha,
                "message": c.subject,
                "author": c.author.name,
                "date": c.committed_date.isoformat(),
                "pr_number": c.pr_number,
            }
            for c in commits
        ],
    }


async def _get_file_at_commit(repo_path: str, sha: str, file_path: str) -> dict[str, Any]:
    """Get file contents at a specific commit."""
    repo = GitRepo(repo_path)
    content = repo.get_file_at_commit(sha, file_path)

    return {
        "success": True,
        "sha": sha,
        "file_path": file_path,
        "content": content,
        "lines": len(content.splitlines()),
    }


def _strip_comment_markers(text: str) -> str:
    """Strip common comment markers to find core content.

    This helps find the true introduction of code even if comment style changed
    (e.g., /* */ to // or vice versa).
    """
    import re

    # Remove common comment prefixes/suffixes
    text = text.strip()
    # Block comments: /* ... */ or /** ... */
    text = re.sub(r"^/\*+\s*", "", text)
    text = re.sub(r"\s*\*+/$", "", text)
    # Line comments: // or #
    text = re.sub(r"^//\s*", "", text)
    text = re.sub(r"^#\s*", "", text)
    # Leading asterisks in block comments (e.g., * line)
    text = re.sub(r"^\*\s*", "", text)
    return text.strip()


def _check_introduced_as_comment(
    repo: "GitRepo",
    origin_sha: str,
    search_string: str,
) -> bool | None:
    """Check if code was introduced as a comment in the origin commit.

    Args:
        repo: GitRepo instance
        origin_sha: The commit SHA where the code was first introduced
        search_string: The code content to look for in the diff

    Returns:
        True if introduced as a comment/placeholder
        False if introduced as active code
        None if could not determine
    """
    try:
        origin_diff = repo.get_diff(origin_sha)
        if not origin_diff:
            return None

        for diff_file in origin_diff:
            for hunk in diff_file.hunks:
                for diff_line in hunk.lines:
                    # Check added lines (+) that contain our search string
                    if diff_line.startswith("+") and search_string in diff_line:
                        # Check if the added line was a comment
                        added_content = diff_line[1:].lstrip()
                        if any(added_content.startswith(m) for m in ("//", "#", "/*", "* ", "*/")):
                            return True
                        else:
                            return False
        return None
    except Exception:
        return None


def _get_grouped_origins(
    repo: "GitRepo",
    content_lines: list[str],
    line_numbers: list[int],
    file_path: str,
    github_base_url: str | None,
    max_lines: int = 25,
    sample_size: int = 10,
) -> list[dict[str, Any]]:
    """Get origin information for lines, grouped by origin SHA.

    For selections with ≤max_lines relevant lines, runs pickaxe for each line.
    For larger selections, samples sample_size lines and assigns unsampled
    lines to the origin of their nearest sampled neighbor.

    Args:
        repo: GitRepo instance
        content_lines: List of line contents
        line_numbers: List of corresponding line numbers
        file_path: Path to the file being analyzed
        github_base_url: Base URL for GitHub links (or None)
        max_lines: Threshold for per-line vs sampled pickaxe
        sample_size: Number of lines to sample for large selections

    Returns:
        List of origin objects, each with:
        - sha, short_sha, author, date, message, html_url
        - lines: list of line numbers with this origin
        - introduced_as_comment: list of line numbers introduced as comments
    """
    # Filter relevant lines (non-blank)
    relevant = [
        (line_num, content)
        for line_num, content in zip(line_numbers, content_lines, strict=False)
        if content.strip()
    ]

    if not relevant:
        return []

    # Decide whether to use per-line or sampled pickaxe
    if len(relevant) <= max_lines:
        lines_to_analyze = relevant
    else:
        # Sample evenly distributed lines
        step = max(1, len(relevant) // sample_size)
        lines_to_analyze = relevant[::step][:sample_size]

    # Cache pickaxe results by search string
    pickaxe_cache: dict[str, list] = {}

    # Map line_number -> origin info
    line_origins: dict[int, dict[str, Any]] = {}

    for line_num, content in lines_to_analyze:
        stripped = content.strip()
        core_content = _strip_comment_markers(stripped)

        # Check cache first
        cache_key = core_content
        if cache_key in pickaxe_cache:
            pickaxe_results = pickaxe_cache[cache_key]
        else:
            try:
                pickaxe_results = repo.pickaxe_search(
                    search_string=core_content,
                    file_path=file_path,
                    max_commits=5,
                    follow_renames=True,
                )
                pickaxe_cache[cache_key] = pickaxe_results
            except Exception:
                pickaxe_results = []

        if pickaxe_results:
            origin_commit = pickaxe_results[-1]  # Oldest is true origin
            origin_sha = origin_commit.sha

            # Check if introduced as comment
            introduced_as_comment = _check_introduced_as_comment(repo, origin_sha, core_content)

            line_origins[line_num] = {
                "sha": origin_sha,
                "short_sha": origin_sha[:7],
                "author": origin_commit.author.name,
                "date": origin_commit.committed_date.isoformat(),
                "message": _truncate(origin_commit.subject, 100),
                "html_url": f"{github_base_url}/commit/{origin_sha}" if github_base_url else None,
                "introduced_as_comment": introduced_as_comment,
            }

    # For large selections, assign unsampled lines to nearest sampled neighbor
    if len(relevant) > max_lines:
        sampled_line_nums = {line_num for line_num, _ in lines_to_analyze}
        for line_num, _ in relevant:
            if line_num not in sampled_line_nums and line_num not in line_origins:
                # Find nearest sampled neighbor
                nearest = min(
                    sampled_line_nums,
                    key=lambda x: abs(x - line_num),
                    default=None,
                )
                if nearest and nearest in line_origins:
                    line_origins[line_num] = line_origins[nearest].copy()

    # Group by origin SHA
    origins_by_sha: dict[str, dict[str, Any]] = {}
    for line_num, origin_info in line_origins.items():
        sha = origin_info["sha"]
        if sha not in origins_by_sha:
            origins_by_sha[sha] = {
                "sha": sha,
                "short_sha": origin_info["short_sha"],
                "author": origin_info["author"],
                "date": origin_info["date"],
                "message": origin_info["message"],
                "html_url": origin_info["html_url"],
                "lines": [],
                "introduced_as_comment": [],
            }
        origins_by_sha[sha]["lines"].append(line_num)
        if origin_info.get("introduced_as_comment") is True:
            origins_by_sha[sha]["introduced_as_comment"].append(line_num)

    # Sort lines within each origin and convert to list
    origins = []
    for origin in origins_by_sha.values():
        origin["lines"].sort()
        origin["introduced_as_comment"].sort()
        origins.append(origin)

    # Sort origins by first line number
    origins.sort(key=lambda o: o["lines"][0] if o["lines"] else 0)

    return origins


async def _pickaxe_search(
    repo_path: str,
    search_string: str,
    file_path: str | None = None,
    max_commits: int = 20,
    regex: bool = False,
    follow_renames: bool = True,
    strip_comments: bool = True,
) -> dict[str, Any]:
    """Find commits that introduced or removed a specific string using git pickaxe.

    When file_path is provided and follow_renames is True (default), this will
    trace through file renames to find the true introduction commit even if the
    file was renamed after the code was added.

    When strip_comments is True (default), common comment markers (// /* */ #)
    are stripped from the search string to find the true introduction even if
    comment style changed over time.
    """
    from ctm_mcp_server.utils import detect_github_remote

    repo = GitRepo(repo_path)

    # Detect GitHub remote for constructing commit URLs
    github_info = detect_github_remote(repo)
    github_base_url = None
    if github_info:
        owner, repo_name = github_info
        github_base_url = f"https://github.com/{owner}/{repo_name}"

    # Try with original string first
    original_search = search_string
    commits = repo.pickaxe_search(
        search_string=search_string,
        file_path=file_path,
        max_commits=max_commits,
        regex=regex,
        follow_renames=follow_renames,
    )

    # If strip_comments is enabled and we got few results, try without comment markers
    stripped_search = None
    if strip_comments and not regex:
        stripped = _strip_comment_markers(search_string)
        if stripped != search_string and len(stripped) > 5:
            stripped_search = stripped
            stripped_commits = repo.pickaxe_search(
                search_string=stripped,
                file_path=file_path,
                max_commits=max_commits,
                regex=regex,
                follow_renames=follow_renames,
            )
            # Use stripped results if they found older commits
            if stripped_commits:
                if not commits:
                    commits = stripped_commits
                elif stripped_commits[-1].committed_date < commits[-1].committed_date:
                    # Stripped search found older commits - use those
                    commits = stripped_commits
                    search_string = stripped

    # Format commits for output
    formatted_commits = []
    for commit in commits:
        commit_data = {
            "sha": commit.sha,
            "short_sha": commit.short_sha,
            "author": commit.author.name,
            "date": commit.committed_date.isoformat(),
            "message": commit.subject,
            "full_message": commit.message,
            "pr_number": commit.pr_number,
            "issue_numbers": commit.issue_numbers,
            "files_changed": len(commit.files_changed),
        }
        # Add GitHub URL if available
        if github_base_url:
            commit_data["html_url"] = f"{github_base_url}/commit/{commit.sha}"
            if commit.pr_number:
                commit_data["pr_url"] = f"{github_base_url}/pull/{commit.pr_number}"
        formatted_commits.append(commit_data)

    # Identify the "introduction" commit (last one in the list = oldest = when code was first added)
    introduction_commit = formatted_commits[-1] if formatted_commits else None

    result: dict[str, Any] = {
        "success": True,
        "search_string": search_string,
        "file_path": file_path,
        "regex": regex,
        "total_commits": len(formatted_commits),
        "commits": formatted_commits,
        "introduction_commit": introduction_commit,
        "note": "The 'introduction_commit' is the oldest commit that added/removed this code (likely when it was first introduced). Commits are ordered newest to oldest. When file_path is provided, file renames are followed by default to find the true origin.",
    }

    # Add GitHub info if available
    if github_info:
        result["github_owner"] = github_info[0]
        result["github_repo"] = github_info[1]
        result["github_base_url"] = github_base_url

    # Add info about stripped search if it was used
    if stripped_search and search_string == stripped_search:
        result["original_search"] = original_search
        result["stripped_search"] = stripped_search
        result["note"] += " Comment markers were stripped to find older commits."

    return result


async def _pickaxe_search_github(
    owner: str,
    repo: str,
    search_string: str,
    path: str | None = None,
    max_commits: int = 20,
    regex: bool = False,
    follow_renames: bool = True,
) -> dict[str, Any]:
    """Find commits that introduced or removed a specific string via GitHub API.

    This is slower than local pickaxe but works for remote repos.
    When path is provided and follow_renames is True (default), this will
    trace through file renames to find the true introduction commit.
    """
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    result = await client.pickaxe_search(
        search_string=search_string,
        path=path,
        max_commits=max_commits,
        regex=regex,
        follow_renames=follow_renames,
    )

    response = {
        "success": True,
        "search_string": search_string,
        "path": path,
        "regex": regex,
        "total_analyzed": result.get("total_analyzed", 0),
        "total_commits": len(result.get("commits", [])),
        "commits": result.get("commits", []),
        "introduction_commit": result.get("introduction_commit"),
        "note": "The 'introduction_commit' is the oldest commit that modified this code (likely when it was first introduced). This uses GitHub API and is slower than local pickaxe_search. When path is provided, file renames are followed by default to find the true origin.",
    }

    # Include rename chain if renames were followed
    if result.get("rename_chain"):
        response["rename_chain"] = result["rename_chain"]

    return response


async def _explain_commit(repo_path: str, sha: str) -> dict[str, Any]:
    """Explain commit intent using heuristics."""
    repo = GitRepo(repo_path)
    commit = repo.get_commit(sha)

    # Intent detection based on commit message
    message_lower = commit.message.lower()
    subject_lower = commit.subject.lower()

    # Keywords for each intent type
    intent_keywords = {
        IntentType.BUGFIX: ["fix", "bug", "issue", "error", "crash", "problem", "resolve", "patch"],
        IntentType.FEATURE: ["add", "implement", "new", "feature", "introduce", "create"],
        IntentType.REFACTOR: [
            "refactor",
            "clean",
            "reorganize",
            "restructure",
            "simplify",
            "improve",
        ],
        IntentType.PERFORMANCE: ["optimize", "perf", "speed", "fast", "cache", "performance"],
        IntentType.SECURITY: ["security", "vulnerability", "cve", "auth", "permission", "sanitize"],
        IntentType.DOCS: ["doc", "readme", "comment", "typo", "documentation"],
        IntentType.TEST: ["test", "spec", "coverage", "mock", "assert"],
        IntentType.CHORE: ["chore", "deps", "dependency", "upgrade", "update", "bump", "version"],
        IntentType.WORKAROUND: ["workaround", "hack", "temp", "todo", "fixme", "wip"],
        IntentType.REVERT: ["revert"],
        IntentType.MERGE: ["merge"],
    }

    # Check for conventional commit prefix
    conventional_match = re.match(r"^(\w+)(?:\(.+\))?!?:", subject_lower)
    conventional_type = conventional_match.group(1) if conventional_match else None

    conventional_mapping = {
        "fix": IntentType.BUGFIX,
        "feat": IntentType.FEATURE,
        "refactor": IntentType.REFACTOR,
        "perf": IntentType.PERFORMANCE,
        "docs": IntentType.DOCS,
        "test": IntentType.TEST,
        "chore": IntentType.CHORE,
        "revert": IntentType.REVERT,
        "style": IntentType.REFACTOR,
        "build": IntentType.CHORE,
        "ci": IntentType.CHORE,
    }

    # Determine intent
    detected_intent = IntentType.UNKNOWN
    confidence = 0.0
    keywords_found: list[str] = []

    # Check conventional commit first (highest confidence)
    if conventional_type and conventional_type in conventional_mapping:
        detected_intent = conventional_mapping[conventional_type]
        confidence = 0.9
        keywords_found.append(f"conventional:{conventional_type}")
    else:
        # Check merge commit
        if commit.is_merge_commit or subject_lower.startswith("merge"):
            detected_intent = IntentType.MERGE
            confidence = 0.95
            keywords_found.append("merge_commit")
        else:
            # Check keywords
            max_matches = 0
            for intent, keywords in intent_keywords.items():
                matches = [kw for kw in keywords if kw in message_lower]
                if len(matches) > max_matches:
                    max_matches = len(matches)
                    detected_intent = intent
                    keywords_found = matches

            if max_matches > 0:
                confidence = min(0.5 + (max_matches * 0.15), 0.85)

    # Generate summary
    summary = f"This appears to be a {detected_intent.value} commit"
    if keywords_found:
        summary += f" based on keywords: {', '.join(keywords_found)}"

    # Build evidence list
    evidence = []
    is_merge = commit.is_merge_commit or subject_lower.startswith("merge")

    if is_merge:
        evidence.append({"source": "commit_type", "signal": "merge commit", "weight": 0.95})
    elif conventional_type:
        evidence.append(
            {"source": "conventional_commit", "signal": f"type: {conventional_type}", "weight": 0.9}
        )
    else:
        for keyword in keywords_found:
            evidence.append(
                {"source": "message_keywords", "signal": f"contains '{keyword}'", "weight": 0.15}
            )

    # Additional evidence sources
    if commit.pr_number:
        evidence.append(
            {
                "source": "pr_reference",
                "signal": f"references PR #{commit.pr_number}",
                "weight": 0.3,
            }
        )
    if commit.issue_numbers:
        for issue_num in commit.issue_numbers[:2]:  # Limit to first 2
            evidence.append(
                {
                    "source": "issue_reference",
                    "signal": f"references issue #{issue_num}",
                    "weight": 0.2,
                }
            )

    # Detect missing context
    missing_context = []
    suggestions = []

    # Check message quality
    if len(commit.message) < 20:
        missing_context.append("short_commit_message")
        suggestions.append("Commit message is very short - consider checking PR description")

    generic_messages = ["fix", "wip", "update", "changes", "stuff", "tmp", "temp", "refactor"]
    if commit.subject.strip().lower() in generic_messages:
        missing_context.append("generic_commit_message")
        suggestions.append("Generic commit message - look for linked PR/issue for context")

    # Check for PR/issue references
    if not commit.pr_number and not commit.issue_numbers:
        missing_context.append("no_linked_pr_or_issue")
        suggestions.append("No PR or issue reference - this may be a direct push")

    # Check file changes
    if not commit.files_changed or len(commit.files_changed) == 0:
        missing_context.append("no_file_changes_analyzed")
        suggestions.append("File diff not available - confidence based on message only")

    return {
        "success": True,
        "sha": commit.short_sha,
        "subject": commit.subject,
        "intent": detected_intent.value,
        "confidence": round(confidence, 2),
        "summary": summary,
        "keywords_found": keywords_found,
        "conventional_commit_type": conventional_type,
        "pr_number": commit.pr_number,
        "issue_numbers": commit.issue_numbers,
        "author": commit.author.name,
        "date": commit.committed_date.isoformat(),
        "evidence": evidence,
        "missing_context": missing_context,
        "suggestions": suggestions,
    }


async def _blame_with_context(
    repo_path: str,
    file_path: str,
    start_line: int | None,
    end_line: int | None,
) -> dict[str, Any]:
    """Enhanced blame with context."""
    repo = GitRepo(repo_path)
    blame_result = repo.get_blame(file_path, start_line=start_line, end_line=end_line)

    # Group lines by commit for summary
    commits_summary: dict[str, dict[str, Any]] = {}
    for line in blame_result.lines:
        if line.commit_sha not in commits_summary:
            commits_summary[line.commit_sha] = {
                "sha": line.commit_short_sha,
                "author": line.author.name,
                "date": line.committed_date.isoformat(),
                "message": line.commit_message,
                "pr_number": line.pr_number,
                "issue_numbers": line.issue_numbers,
                "line_count": 0,
            }
        commits_summary[line.commit_sha]["line_count"] += 1

    return {
        "success": True,
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "total_lines": len(blame_result.lines),
        "unique_commits": len(commits_summary),
        "commits_summary": list(commits_summary.values()),
        "lines": [
            {
                "line_number": line.line_number,
                "content": line.content[:200],  # Truncate long lines
                "sha": line.commit_short_sha,
                "author": line.author.name,
                "date": line.committed_date.isoformat(),
                "pr_number": line.pr_number,
            }
            for line in blame_result.lines[:100]  # Limit output
        ],
    }


async def _get_local_line_context(
    repo_path: str,
    file_path: str,
    line_start: int,
    line_end: int | None = None,
    include_discussions: bool = True,
    history_depth: int = 1,
    ref: str | None = None,
    include_nearby_context: bool = True,
) -> dict[str, Any]:
    """Get line context for local repo using LOCAL git blame, enriched with GitHub context.

    IMPORTANT: Always uses local git blame first to get accurate commit attribution
    for the specific lines requested. This is more accurate than GitHub API's file
    history which only shows recent commits, not the actual commits that touched
    specific lines.

    If local repo has GitHub remote, enriches blame results with PR/issue context.

    Args:
        ref: Git ref (branch, tag, or SHA) to analyze. Defaults to HEAD.
        history_depth: Number of historical commits to analyze for finding when
            code was originally introduced (useful when recent commits only modified
            surrounding code).
        include_nearby_context: Check lines before/after selection for related code.
            Helps detect patterns like commented code with active alternatives.
    """
    from ctm_mcp_server.utils import detect_github_remote

    repo = GitRepo(repo_path)
    github_info = detect_github_remote(repo)

    # If no ref specified, use current branch
    if ref is None:
        ref = repo.current_branch or "HEAD"

    line_end = line_end or line_start

    # ALWAYS use local git blame first - this gives accurate per-line attribution
    try:
        blame_result = repo.get_blame(file_path, start_line=line_start, end_line=line_end)
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to get blame: {e}",
            "file_path": file_path,
            "line_range": [line_start, line_end],
        }

    # Collect ALL unique blame commits for the requested lines
    commit_info: dict[str, dict[str, Any]] = {}
    commit_counts: dict[str, int] = {}
    commit_lines: dict[str, list[int]] = {}  # Track which lines each commit modified

    for line in blame_result.lines:
        sha = line.commit_sha
        commit_counts[sha] = commit_counts.get(sha, 0) + 1
        if sha not in commit_lines:
            commit_lines[sha] = []
        commit_lines[sha].append(line.line_number)

        if sha not in commit_info:
            # Filter out PR number from issue_numbers - PR #230 shouldn't appear as issue #230
            filtered_issues = [n for n in (line.issue_numbers or []) if n != line.pr_number]
            commit_info[sha] = {
                "sha": sha,
                "message": line.commit_message,
                "author": line.author.name,
                "date": line.committed_date.isoformat(),
                "message_signals": _extract_message_signals(line.commit_message),
                "pr_number": line.pr_number,
                "issue_numbers": filtered_issues,
            }

    if not commit_counts:
        return {
            "success": False,
            "error": "No blame information found for the specified lines",
            "file_path": file_path,
            "line_range": [line_start, line_end],
        }

    # Primary blame commit is the one that touched most of the requested lines
    primary_sha = max(commit_counts, key=commit_counts.get)  # type: ignore
    primary_line = next(bl for bl in blame_result.lines if bl.commit_sha == primary_sha)

    # Build blame_commits array with ALL unique commits, ordered by line count
    blame_commits_list = []
    for sha in sorted(commit_counts.keys(), key=lambda s: commit_counts[s], reverse=True):
        info = commit_info[sha].copy()
        info["line_count"] = commit_counts[sha]
        info["lines"] = commit_lines[sha]
        blame_commits_list.append(info)

    # Get current content
    current_content = "\n".join(line.content for line in blame_result.lines)

    # Build GitHub URLs if available
    github_base_url = None
    if github_info:
        owner, repo_name = github_info
        github_base_url = f"https://github.com/{owner}/{repo_name}"

    # Add URLs to blame commits
    for bc in blame_commits_list:
        if github_base_url:
            bc["html_url"] = f"{github_base_url}/commit/{bc['sha']}"
            if bc.get("pr_number"):
                bc["pr_url"] = f"{github_base_url}/pull/{bc['pr_number']}"

    # Build code_sections: group consecutive lines by their origin commit
    # This provides a pre-analyzed breakdown for the agent
    code_sections: list[dict[str, Any]] = []
    if blame_result.lines:
        current_section: dict[str, Any] | None = None

        for line in blame_result.lines:
            sha = line.commit_sha
            if current_section is None or current_section["commit_sha"] != sha:
                # Start new section
                if current_section is not None:
                    code_sections.append(current_section)

                # Get commit info for this section
                ci = commit_info.get(sha, {})
                current_section = {
                    "lines": [line.line_number],
                    "line_start": line.line_number,
                    "line_end": line.line_number,
                    "content": [line.content],
                    "commit_sha": sha,
                    "commit_short_sha": sha[:7],
                    "author": ci.get("author", line.author.name),
                    "date": ci.get("date", line.committed_date.isoformat()),
                    "message": ci.get("message", line.commit_message),
                    "pr_number": ci.get("pr_number"),
                    "html_url": f"{github_base_url}/commit/{sha}" if github_base_url else None,
                    "pr_url": f"{github_base_url}/pull/{ci.get('pr_number')}"
                    if github_base_url and ci.get("pr_number")
                    else None,
                }
            else:
                # Extend current section
                current_section["lines"].append(line.line_number)
                current_section["line_end"] = line.line_number
                current_section["content"].append(line.content)

        # Don't forget the last section
        if current_section is not None:
            code_sections.append(current_section)

        # Convert content arrays to strings
        for section in code_sections:
            section["content"] = "\n".join(section["content"])
            section["line_range"] = (
                f"{section['line_start']}-{section['line_end']}"
                if section["line_start"] != section["line_end"]
                else str(section["line_start"])
            )

        # AUTO-PICKAXE: Find true origin for each code section
        # This eliminates the need for the agent to manually call pickaxe_search
        # Uses per-line pickaxe for accurate origin detection (≤25 lines)
        # or sampled pickaxe for larger selections
        for section in code_sections:
            section["origins"] = []  # List of origins grouped by SHA
            section["is_currently_commented"] = False  # Track if section is commented code
            try:
                content_lines = section["content"].split("\n")
                line_numbers = section["lines"]

                # Check if the section is currently commented
                # A section is considered commented if ALL non-empty lines start with comment markers
                non_empty_lines = [line.strip() for line in content_lines if line.strip()]
                if non_empty_lines and all(
                    line.startswith("//")
                    or line.startswith("#")
                    or line.startswith("/*")
                    or line.startswith("*")
                    for line in non_empty_lines
                ):
                    section["is_currently_commented"] = True

                # Get grouped origins using per-line pickaxe
                section["origins"] = _get_grouped_origins(
                    repo=repo,
                    content_lines=content_lines,
                    line_numbers=line_numbers,
                    file_path=file_path,
                    github_base_url=github_base_url,
                    max_lines=25,
                    sample_size=10,
                )
            except Exception as e:
                # Pickaxe failed for this section - not critical, continue
                section["origin_error"] = str(e)

    # Build result - NOTE: blame shows LAST TOUCH, not original introduction
    result: dict[str, Any] = {
        "file_path": file_path,
        "line_range": [line_start, line_end],
        "current_content": current_content,
        # Explanation of what this data means - helps agent understand the difference
        "interpretation": "Each code section includes 'origins' (list of origin commits grouped by SHA, each with 'lines' array). The 'introduced_as_comment' field lists line numbers that were introduced as comments. Lines in 'lines' but NOT in 'introduced_as_comment' were introduced as active code.",
        # Primary commit that last modified these lines (clearer name)
        "last_modified_by": {
            "sha": primary_sha,
            "message": primary_line.commit_message,
            "author": primary_line.author.name,
            "date": primary_line.committed_date.isoformat(),
            "message_signals": _extract_message_signals(primary_line.commit_message),
            "html_url": f"{github_base_url}/commit/{primary_sha}" if github_base_url else None,
            "note": "This is the LAST TOUCH, not necessarily the original author",
        },
        # Backwards compatible alias
        "blame_commit": {
            "sha": primary_sha,
            "message": primary_line.commit_message,
            "author": primary_line.author.name,
            "date": primary_line.committed_date.isoformat(),
            "message_signals": _extract_message_signals(primary_line.commit_message),
            "html_url": f"{github_base_url}/commit/{primary_sha}" if github_base_url else None,
        },
        # Pre-analyzed code sections grouped by last-touch commit
        "code_sections": code_sections,
        "historical_commits": [],
        "pull_request": None,
        "linked_issues": [],
        "github_remote": {"owner": github_info[0], "repo": github_info[1]} if github_info else None,
        "context_availability": {
            "available": ["file_content", "commit"],
            "missing": [],
            "confidence_hint": "medium",
            "suggestions": [],
        },
    }

    # Add note if multiple commits touch the selected lines
    if len(blame_commits_list) > 1:
        result["context_availability"]["suggestions"].append(
            f"Note: {len(blame_commits_list)} different commits modified the selected lines"
        )

    # Get historical commits if requested (using pickaxe with --follow for accuracy)
    if history_depth > 1:
        try:
            # Use the actual line content to find when it was introduced
            # Take a representative line from the blamed content
            search_content = blame_result.lines[0].content.strip() if blame_result.lines else None
            if search_content and len(search_content) > 10:
                historical = repo.pickaxe_search(
                    search_string=search_content,
                    file_path=file_path,
                    max_commits=history_depth,
                    follow_renames=True,
                )
                # Skip the first if it matches primary (avoid duplicate)
                for commit in historical:
                    if commit.sha != primary_sha:
                        result["historical_commits"].append(
                            {
                                "sha": commit.sha,
                                "message": _truncate(commit.subject, 300),
                                "author": commit.author.name,
                                "date": commit.committed_date.isoformat(),
                                "message_signals": _extract_message_signals(commit.message),
                                "stats": {
                                    "additions": sum(
                                        f.additions
                                        for f in commit.files_changed
                                        if hasattr(f, "additions")
                                    ),
                                    "deletions": sum(
                                        f.deletions
                                        for f in commit.files_changed
                                        if hasattr(f, "deletions")
                                    ),
                                    "total": len(commit.files_changed),
                                },
                            }
                        )
                if result["historical_commits"]:
                    result["context_availability"]["available"].append("historical_commits")
                    result["context_availability"]["suggestions"].append(
                        f"Found {len(result['historical_commits'])} historical commits for deeper context"
                    )
        except Exception:
            pass  # Historical commits are optional enhancement

    if github_info:
        # Enrich with GitHub PR/issue context
        owner, repo_name = github_info
        result["source"] = "github_remote"
        result["remote_url"] = f"https://github.com/{owner}/{repo_name}"
        result["ref"] = ref

        try:
            client = GitHubClient(owner=owner, repo=repo_name, cache=_cache)

            # Find PR for the blame commit
            prs = await client.search_prs_for_commit(primary_sha)

            if prs and len(prs) > 0:
                # search_prs_for_commit returns list of PR numbers (integers)
                pr_number = prs[0]
                pr_detail = await client.get_pull_request(pr_number)

                result["pull_request"] = {
                    "number": pr_number,
                    "title": pr_detail.title,
                    "body": _truncate(pr_detail.body or "", 500),
                    "author": pr_detail.author.login if pr_detail.author else "",
                    "state": pr_detail.state,
                    "relevant_discussions": [],
                    "review_summary": None,
                }
                result["context_availability"]["available"].append("pull_request")

                # Get PR discussions if requested
                if include_discussions:
                    try:
                        comments = await client.get_pr_comments(pr_number)
                        review_comments = await client.get_pr_review_comments(pr_number)
                        all_comments = comments + review_comments
                        relevant = _filter_relevant_discussions(all_comments)
                        result["pull_request"]["relevant_discussions"] = relevant[:5]

                        reviews = await client.get_pr_reviews(pr_number)
                        result["pull_request"]["review_summary"] = _summarize_reviews(reviews)
                    except Exception:
                        pass

                # Find linked issues from multiple sources:
                # 1. Text-based: Parse PR title, body, and commit message for issue references
                issue_refs_text = _extract_issue_references(
                    (pr_detail.title or "")
                    + " "
                    + (pr_detail.body or "")
                    + " "
                    + primary_line.commit_message
                )
                # 2. API-based: Get issues linked via GitHub's Development sidebar
                try:
                    issue_refs_api = await client.get_pr_linked_issues(pr_number)
                except Exception:
                    issue_refs_api = []

                # Combine and deduplicate, excluding the PR number itself
                issue_refs = list(set(issue_refs_text + issue_refs_api))
                issue_refs = [n for n in issue_refs if n != pr_number]

                for issue_num in issue_refs[:3]:
                    try:
                        issue = await client.get_issue(issue_num)
                        result["linked_issues"].append(
                            {
                                "number": issue_num,
                                "title": issue.title,
                                "body": issue.body[:500] if issue.body else None,
                                "author": issue.author.login if issue.author else None,
                                "labels": [label.name for label in issue.labels],
                                "state": issue.state,
                                "html_url": issue.html_url,
                            }
                        )
                    except Exception:
                        pass

                if result["linked_issues"]:
                    result["context_availability"]["available"].append("linked_issues")

            result["context_availability"]["confidence_hint"] = (
                "high" if result["pull_request"] else "medium"
            )

        except Exception as e:
            result["context_availability"]["missing"].append("pull_request")
            result["context_availability"]["suggestions"].append(
                f"Could not fetch GitHub context: {e}"
            )
    else:
        # No GitHub remote
        result["source"] = "local_only"
        result["context_availability"]["missing"].extend(["pull_request", "linked_issues"])
        result["context_availability"]["suggestions"].append(
            "Add a GitHub remote for full PR/issue context"
        )

    # === NEW: Pattern detection, quick answer, and confidence scoring ===

    # Get nearby context if enabled (helps detect active alternatives)
    nearby_context = None
    if include_nearby_context:
        nearby_context = _get_nearby_context(repo, file_path, line_start, line_end)
        if nearby_context:
            result["nearby_context"] = nearby_context

    # Detect patterns (commented code, TODOs, etc.)
    patterns = _detect_patterns(
        code_sections,
        nearby_context,
        result.get("pull_request"),
        result.get("linked_issues", []),
    )
    if patterns:
        result["patterns_detected"] = patterns

    # Generate quick answer if pattern is clear
    quick_answer = _generate_quick_answer(
        code_sections,
        patterns,
        result.get("pull_request"),
        result.get("linked_issues", []),
    )
    if quick_answer:
        result["quick_answer"] = quick_answer

    # Calculate confidence with specific signals
    confidence = _calculate_confidence(
        code_sections,
        result.get("pull_request"),
        result.get("linked_issues", []),
        patterns,
        nearby_context,
    )
    result["confidence"] = confidence
    # Keep backwards-compatible confidence_hint
    result["context_availability"]["confidence_hint"] = confidence["level"]

    return result


# GitHub API tool implementations
async def _get_github_repo(owner: str, repo: str) -> dict[str, Any]:
    """Get GitHub repository info via API."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    info = await client.get_repo_info()

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        **info,
    }


async def _get_github_branches(owner: str, repo: str) -> dict[str, Any]:
    """Get GitHub repository branches via API."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    branches = await client.get_branches()

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "branches": branches,
    }


async def _get_github_commit(owner: str, repo: str, sha: str) -> dict[str, Any]:
    """Get GitHub commit details via API (optimized for token efficiency)."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    commit = await client.get_commit(sha)

    # Remove patch data to reduce token usage (can be very large)
    # Keep only file metadata
    files_summary = [
        {
            "path": f["path"],
            "status": f["status"],
            "additions": f["additions"],
            "deletions": f["deletions"],
            # Omit "patch" - too verbose
        }
        for f in commit.get("files", [])[:20]  # Limit to 20 files
    ]

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "sha": commit["sha"],
        "message": _truncate(commit["message"], 500),
        "author": commit["author"],
        "committer": commit["committer"],
        "parents": commit["parents"],
        "stats": commit["stats"],
        "html_url": commit["html_url"],
        "total_files": len(commit.get("files", [])),
        "files": files_summary,
    }


async def _get_github_commits_batch(owner: str, repo: str, shas: list[str]) -> dict[str, Any]:
    """Get multiple GitHub commits at once (batch operation).

    This is much more efficient than calling _get_github_commit multiple times.
    Uses caching and fetches missing commits in parallel.

    Args:
        owner: Repository owner
        repo: Repository name
        shas: List of commit SHAs to fetch

    Returns:
        Dictionary with:
        - success: True/False
        - commits: Dictionary mapping SHA -> commit details
        - total_requested: Number of SHAs requested
        - total_found: Number of commits successfully retrieved
        - missing_shas: List of SHAs that couldn't be found
    """
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)

    # Fetch all commits in batch
    commits_dict = await client.get_commits_batch(shas)

    # Format each commit (similar to _get_github_commit)
    formatted_commits = {}
    for sha, commit in commits_dict.items():
        # Remove patch data to reduce token usage
        files_summary = [
            {
                "path": f["path"],
                "status": f["status"],
                "additions": f["additions"],
                "deletions": f["deletions"],
            }
            for f in commit.get("files", [])[:20]
        ]

        formatted_commits[sha] = {
            "sha": commit["sha"],
            "message": _truncate(commit["message"], 500),
            "author": commit["author"],
            "committer": commit["committer"],
            "parents": commit["parents"],
            "stats": commit["stats"],
            "html_url": commit["html_url"],
            "total_files": len(commit.get("files", [])),
            "files": files_summary,
        }

    # Identify missing SHAs
    missing_shas = [sha for sha in shas if sha not in commits_dict]

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "commits": formatted_commits,
        "total_requested": len(shas),
        "total_found": len(formatted_commits),
        "missing_shas": missing_shas,
    }


async def _get_github_file_history(
    owner: str, repo: str, path: str, max_commits: int
) -> dict[str, Any]:
    """Get file commit history via GitHub API."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    commits = await client.list_commits(path=path, per_page=max_commits)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "path": path,
        "total_commits": len(commits),
        "commits": commits,
    }


async def _get_github_file(
    owner: str, repo: str, path: str, ref: str | None, max_size: int = 50000
) -> dict[str, Any]:
    """Get file contents via GitHub API (with configurable size limit for token efficiency)."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    file_data = await client.get_file_contents(path, ref=ref)

    # Truncate large files to prevent token explosion
    # max_size=0 means no limit, otherwise truncate at max_size
    content = file_data.get("content", "")
    is_truncated = False
    if max_size > 0 and len(content) > max_size:
        content = (
            content[:max_size]
            + f"\n... [truncated at {max_size} bytes - use max_size=0 for full content]"
        )
        is_truncated = True

    result = {
        "success": True,
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "type": file_data.get("type"),
        "path": file_data.get("path"),
        "name": file_data.get("name"),
        "size": file_data.get("size"),
        "html_url": file_data.get("html_url"),
    }

    if file_data.get("type") == "file":
        result["content"] = content
        result["is_truncated"] = is_truncated
    elif file_data.get("type") == "directory":
        result["entries"] = file_data.get("entries", [])[:50]  # Limit directory entries

    return result


def _truncate(text: str | None, max_len: int = 500) -> str | None:
    """Truncate text to reduce token usage."""
    if not text:
        return text
    if len(text) <= max_len:
        return text
    return text[:max_len] + "... [truncated]"


async def _get_pr(owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    """Get PR details via GitHub API (optimized for token efficiency)."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    pr = await client.get_pull_request(pr_number)

    # Limit and summarize to reduce token usage
    MAX_COMMENTS = 10
    MAX_REVIEWS = 5
    MAX_REVIEW_COMMENTS = 10

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "pr": {
            "number": pr.number,
            "title": pr.title,
            "body": _truncate(pr.body, 1000),  # Truncate long PR bodies
            "state": pr.state.value,
            "author": pr.author.login,
            "labels": [lbl.name for lbl in pr.labels],
            "assignees": [usr.login for usr in pr.assignees],
            "reviewers": [usr.login for usr in pr.reviewers],
            "created_at": pr.created_at.isoformat() if pr.created_at else None,
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
            "merged_by": pr.merged_by.login if pr.merged_by else None,
            "head_ref": pr.head_ref,
            "base_ref": pr.base_ref,
            "is_merged": pr.is_merged,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": pr.changed_files,
            "commits_count": pr.commits_count,
            "linked_issues": pr.linked_issues,
            "html_url": pr.html_url,
            # Counts for awareness
            "total_comments": len(pr.comments),
            "total_reviews": len(pr.reviews),
            "total_review_comments": len(pr.review_comments),
            # Limited data
            "comments": [
                {
                    "author": c.author.login,
                    "body": _truncate(c.body, 300),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in pr.comments[:MAX_COMMENTS]
            ],
            "reviews": [
                {
                    "author": r.author.login,
                    "state": r.state.value,
                    "body": _truncate(r.body, 200),
                }
                for r in pr.reviews[:MAX_REVIEWS]
            ],
            "review_comments": [
                {
                    "author": c.author.login,
                    "body": _truncate(c.body, 200),
                    "path": c.path,
                    "line": c.line,
                }
                for c in pr.review_comments[:MAX_REVIEW_COMMENTS]
            ],
        },
    }


async def _get_issue(owner: str, repo: str, issue_number: int) -> dict[str, Any]:
    """Get issue details via GitHub API (optimized for token efficiency)."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    issue = await client.get_issue(issue_number)

    MAX_COMMENTS = 10

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "issue": {
            "number": issue.number,
            "title": issue.title,
            "body": _truncate(issue.body, 1000),
            "state": issue.state.value,
            "author": issue.author.login,
            "labels": [lbl.name for lbl in issue.labels],
            "assignees": [usr.login for usr in issue.assignees],
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
            "total_comments": issue.comments_count,
            "html_url": issue.html_url,
            "comments": [
                {
                    "author": c.author.login,
                    "body": _truncate(c.body, 300),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in issue.comments[:MAX_COMMENTS]
            ],
        },
    }


async def _search_prs_for_commit(owner: str, repo: str, sha: str) -> dict[str, Any]:
    """Search for PRs containing a commit via GitHub API.

    Returns both PR numbers and basic details (title, state, author) for each PR found.
    """
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    pr_numbers = await client.search_prs_for_commit(sha)

    # Fetch basic details for each PR found
    prs_with_details = []
    for pr_num in pr_numbers[:5]:  # Limit to first 5 PRs to avoid too many API calls
        try:
            pr_detail = await client.get_pull_request(pr_num)
            prs_with_details.append(
                {
                    "number": pr_num,
                    "title": pr_detail.title,
                    "state": pr_detail.state,
                    "author": pr_detail.author.login if pr_detail.author else None,
                    "html_url": f"https://github.com/{owner}/{repo}/pull/{pr_num}",
                    "merged_at": pr_detail.merged_at.isoformat() if pr_detail.merged_at else None,
                    "body": _truncate(pr_detail.body or "", 300),
                }
            )
        except Exception:
            # If we can't get details, include just the number
            prs_with_details.append(
                {
                    "number": pr_num,
                    "title": None,
                    "state": None,
                    "author": None,
                    "html_url": f"https://github.com/{owner}/{repo}/pull/{pr_num}",
                }
            )

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "sha": sha,
        "pr_numbers": pr_numbers,
        "prs": prs_with_details,  # NEW: Include full PR details
        "total_found": len(pr_numbers),
    }


# Search tool implementations
async def _search_github_code(owner: str, repo: str, query: str, per_page: int) -> dict[str, Any]:
    """Search for code in a GitHub repository."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    results = await client.search_code(query, per_page=per_page)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "query": query,
        "total_count": results["total_count"],
        "incomplete_results": results["incomplete_results"],
        "items": results["items"],
        "hint": "Use get_github_file to fetch the actual content of matching files.",
    }


async def _search_github_commits(
    owner: str, repo: str, query: str, per_page: int
) -> dict[str, Any]:
    """Search for commits in a GitHub repository."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    results = await client.search_commits(query, per_page=per_page)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "query": query,
        "total_count": results["total_count"],
        "incomplete_results": results["incomplete_results"],
        "items": results["items"],
        "hint": "Use get_github_commit for full details of a specific commit.",
    }


# Symbol tracking tool implementations
async def _get_file_symbols(file_path: str) -> dict[str, Any]:
    """Extract symbols from a local file."""
    parser = CodeParser()
    symbols = parser.extract_symbols_from_file(file_path)

    # Group by type for better overview
    functions = [s for s in symbols if s.type.value == "function"]
    methods = [s for s in symbols if s.type.value == "method"]
    classes = [s for s in symbols if s.type.value == "class"]

    return {
        "success": True,
        "file_path": file_path,
        "language": parser.detect_language(file_path),
        "total_symbols": len(symbols),
        "summary": {
            "functions": len(functions),
            "methods": len(methods),
            "classes": len(classes),
        },
        "symbols": [
            {
                "name": s.name,
                "qualified_name": s.qualified_name,
                "type": s.type.value,
                "start_line": s.start_line,
                "end_line": s.end_line,
                "line_count": s.line_count,
                "signature": s.signature,
                "docstring": _truncate(s.docstring, 200) if s.docstring else None,
                "decorators": s.decorators,
                "bases": s.bases if s.bases else None,
            }
            for s in symbols
        ],
    }


async def _get_github_file_symbols(
    owner: str, repo: str, path: str, ref: str | None
) -> dict[str, Any]:
    """Extract symbols from a GitHub file without cloning."""
    # First fetch the file content
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    file_data = await client.get_file_contents(path, ref=ref)

    if file_data.get("type") != "file":
        return {
            "success": False,
            "error": f"Path is not a file: {path}",
        }

    content = file_data.get("content", "")
    if not content:
        return {
            "success": False,
            "error": "File content is empty",
        }

    # Detect language from path
    parser = CodeParser()
    language = parser.detect_language(path)

    if not language:
        return {
            "success": False,
            "error": f"Unsupported file type for symbol extraction: {path}",
        }

    # Parse and extract symbols
    symbols = parser.extract_symbols(content, language)

    # Group by type
    functions = [s for s in symbols if s.type.value == "function"]
    methods = [s for s in symbols if s.type.value == "method"]
    classes = [s for s in symbols if s.type.value == "class"]

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "path": path,
        "ref": ref,
        "language": language,
        "total_symbols": len(symbols),
        "summary": {
            "functions": len(functions),
            "methods": len(methods),
            "classes": len(classes),
        },
        "symbols": [
            {
                "name": s.name,
                "qualified_name": s.qualified_name,
                "type": s.type.value,
                "start_line": s.start_line,
                "end_line": s.end_line,
                "line_count": s.line_count,
                "signature": s.signature,
                "docstring": _truncate(s.docstring, 200) if s.docstring else None,
                "decorators": s.decorators,
                "bases": s.bases if s.bases else None,
            }
            for s in symbols
        ],
    }


async def _trace_symbol_history(
    repo_path: str, file_path: str, symbol_name: str, max_commits: int
) -> dict[str, Any]:
    """Track a symbol's history across commits."""
    repo = GitRepo(repo_path)
    parser = CodeParser()

    # Get file history
    commits = repo.get_file_history(file_path, max_commits=max_commits)

    if not commits:
        return {
            "success": False,
            "error": f"No commits found for file: {file_path}",
        }

    # Track symbol across commits
    changes: list[dict[str, Any]] = []
    prev_symbol = None
    first_seen = None
    last_modified = None

    # Process commits from oldest to newest
    for commit in reversed(commits):
        try:
            # Get file at this commit
            content = repo.get_file_at_commit(commit.sha, file_path)
            language = parser.detect_language(file_path)

            if not language:
                continue

            # Extract symbols
            symbols = parser.extract_symbols(content, language)

            # Find our target symbol (match by name or qualified_name)
            current_symbol = None
            for s in symbols:
                if s.name == symbol_name or s.qualified_name == symbol_name:
                    current_symbol = s
                    break

            # Determine what changed
            if current_symbol and not prev_symbol:
                # Symbol was added
                changes.append(
                    {
                        "sha": commit.short_sha,
                        "date": commit.committed_date.isoformat(),
                        "author": commit.author.name,
                        "message": commit.subject,
                        "change_type": "added",
                        "start_line": current_symbol.start_line,
                        "end_line": current_symbol.end_line,
                        "line_count": current_symbol.line_count,
                        "pr_number": commit.pr_number,
                    }
                )
                first_seen = commit.short_sha
                last_modified = commit.short_sha
            elif current_symbol and prev_symbol:
                # Check if symbol was modified (line numbers or signature changed)
                is_modified = (
                    current_symbol.start_line != prev_symbol.start_line
                    or current_symbol.end_line != prev_symbol.end_line
                    or current_symbol.signature != prev_symbol.signature
                )
                if is_modified:
                    changes.append(
                        {
                            "sha": commit.short_sha,
                            "date": commit.committed_date.isoformat(),
                            "author": commit.author.name,
                            "message": commit.subject,
                            "change_type": "modified",
                            "old_start_line": prev_symbol.start_line,
                            "old_end_line": prev_symbol.end_line,
                            "new_start_line": current_symbol.start_line,
                            "new_end_line": current_symbol.end_line,
                            "lines_changed": abs(
                                current_symbol.line_count - prev_symbol.line_count
                            ),
                            "pr_number": commit.pr_number,
                        }
                    )
                    last_modified = commit.short_sha
            elif not current_symbol and prev_symbol:
                # Symbol was deleted
                changes.append(
                    {
                        "sha": commit.short_sha,
                        "date": commit.committed_date.isoformat(),
                        "author": commit.author.name,
                        "message": commit.subject,
                        "change_type": "deleted",
                        "last_start_line": prev_symbol.start_line,
                        "last_end_line": prev_symbol.end_line,
                        "pr_number": commit.pr_number,
                    }
                )

            prev_symbol = current_symbol

        except (GitRepoError, ParserError):
            # Skip commits where we can't parse the file
            continue

    # Get current state
    current_state = None
    if prev_symbol:
        current_state = {
            "exists": True,
            "start_line": prev_symbol.start_line,
            "end_line": prev_symbol.end_line,
            "line_count": prev_symbol.line_count,
            "signature": prev_symbol.signature,
            "type": prev_symbol.type.value,
        }
    else:
        current_state = {"exists": False}

    return {
        "success": True,
        "symbol_name": symbol_name,
        "file_path": file_path,
        "total_commits_analyzed": len(commits),
        "total_changes": len(changes),
        "first_seen_commit": first_seen,
        "last_modified_commit": last_modified,
        "current_state": current_state,
        "changes": changes,
    }


async def _trace_github_symbol_history(
    owner: str, repo: str, path: str, symbol_name: str, max_commits: int
) -> dict[str, Any]:
    """Track a symbol's history across commits via GitHub API."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    parser = CodeParser()

    # Check language support
    language = parser.detect_language(path)
    if not language:
        return {
            "success": False,
            "error": f"Unsupported file type for symbol extraction: {path}",
        }

    # Get file history
    commits = await client.list_commits(path=path, per_page=max_commits)

    if not commits:
        return {
            "success": False,
            "error": f"No commits found for file: {path}",
        }

    # Track symbol across commits (oldest to newest)
    changes: list[dict[str, Any]] = []
    prev_symbol = None
    first_seen = None
    last_modified = None
    parse_errors = 0

    for commit in reversed(commits):
        try:
            # Fetch file content at this commit
            file_data = await client.get_file_contents(path, ref=commit["sha"])

            if file_data.get("type") != "file":
                continue

            content = file_data.get("content", "")
            if not content:
                continue

            # Extract symbols
            symbols = parser.extract_symbols(content, language)

            # Find target symbol
            current_symbol = None
            for s in symbols:
                if s.name == symbol_name or s.qualified_name == symbol_name:
                    current_symbol = s
                    break

            # Determine what changed
            short_sha = commit["sha"][:7]
            commit_date = commit["author"]["date"]
            author_name = commit["author"]["name"]
            subject = commit["subject"]

            if current_symbol and not prev_symbol:
                # Symbol was added
                changes.append(
                    {
                        "sha": short_sha,
                        "date": commit_date,
                        "author": author_name,
                        "message": subject,
                        "change_type": "added",
                        "start_line": current_symbol.start_line,
                        "end_line": current_symbol.end_line,
                        "line_count": current_symbol.line_count,
                        "html_url": commit.get("html_url"),
                    }
                )
                first_seen = short_sha
                last_modified = short_sha

            elif current_symbol and prev_symbol:
                # Check if modified
                is_modified = (
                    current_symbol.start_line != prev_symbol.start_line
                    or current_symbol.end_line != prev_symbol.end_line
                    or current_symbol.signature != prev_symbol.signature
                )
                if is_modified:
                    changes.append(
                        {
                            "sha": short_sha,
                            "date": commit_date,
                            "author": author_name,
                            "message": subject,
                            "change_type": "modified",
                            "old_start_line": prev_symbol.start_line,
                            "old_end_line": prev_symbol.end_line,
                            "new_start_line": current_symbol.start_line,
                            "new_end_line": current_symbol.end_line,
                            "lines_changed": abs(
                                current_symbol.line_count - prev_symbol.line_count
                            ),
                            "html_url": commit.get("html_url"),
                        }
                    )
                    last_modified = short_sha

            elif not current_symbol and prev_symbol:
                # Symbol was deleted
                changes.append(
                    {
                        "sha": short_sha,
                        "date": commit_date,
                        "author": author_name,
                        "message": subject,
                        "change_type": "deleted",
                        "last_start_line": prev_symbol.start_line,
                        "last_end_line": prev_symbol.end_line,
                        "html_url": commit.get("html_url"),
                    }
                )

            prev_symbol = current_symbol

        except (GitHubClientError, ParserError):
            parse_errors += 1
            continue

    # Current state
    current_state = None
    if prev_symbol:
        current_state = {
            "exists": True,
            "start_line": prev_symbol.start_line,
            "end_line": prev_symbol.end_line,
            "line_count": prev_symbol.line_count,
            "signature": prev_symbol.signature,
            "type": prev_symbol.type.value,
        }
    else:
        current_state = {"exists": False}

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "path": path,
        "symbol_name": symbol_name,
        "total_commits_analyzed": len(commits),
        "total_changes": len(changes),
        "parse_errors": parse_errors,
        "first_seen_commit": first_seen,
        "last_modified_commit": last_modified,
        "current_state": current_state,
        "changes": changes,
    }


# Analysis tool implementations
async def _get_code_owners(owner: str, repo: str, path: str, max_commits: int) -> dict[str, Any]:
    """Find who knows this code best by analyzing commit history."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)

    # Get commits for this path
    commits = await client.list_commits(path=path, per_page=max_commits)

    if not commits:
        return {
            "success": False,
            "error": f"No commits found for path: {path}",
        }

    # Aggregate by author
    author_stats: dict[str, dict[str, Any]] = {}

    for i, commit in enumerate(commits):
        author_name = commit["author"]["name"]
        author_email = commit["author"]["email"]
        key = f"{author_name} <{author_email}>"

        if key not in author_stats:
            author_stats[key] = {
                "name": author_name,
                "email": author_email,
                "commits": 0,
                "first_commit_date": commit["author"]["date"],
                "last_commit_date": commit["author"]["date"],
                "recency_rank": i + 1,  # Lower is more recent
            }

        author_stats[key]["commits"] += 1
        # Track date range
        if commit["author"]["date"]:
            author_stats[key]["last_commit_date"] = commit["author"]["date"]

    # Calculate ownership score
    total_commits = len(commits)
    owners = []

    for _key, stats in author_stats.items():
        # Score based on: commits (50%), recency (50%)
        commit_score = stats["commits"] / total_commits
        recency_score = 1 - (stats["recency_rank"] / total_commits)
        ownership_score = (commit_score * 0.5) + (recency_score * 0.5)

        owners.append(
            {
                "name": stats["name"],
                "email": stats["email"],
                "commits": stats["commits"],
                "commit_percentage": round(commit_score * 100, 1),
                "last_commit_date": stats["last_commit_date"],
                "ownership_score": round(ownership_score, 3),
            }
        )

    # Sort by ownership score
    owners.sort(key=lambda x: x["ownership_score"], reverse=True)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "path": path,
        "total_commits_analyzed": total_commits,
        "unique_contributors": len(owners),
        "owners": owners[:10],  # Top 10
    }


async def _get_change_coupling(
    owner: str, repo: str, path: str, max_commits: int, min_coupling: float
) -> dict[str, Any]:
    """Find files that frequently change together with the target file."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)

    # Get commits that touched this file
    commits = await client.list_commits(path=path, per_page=max_commits)

    if not commits:
        return {
            "success": False,
            "error": f"No commits found for file: {path}",
        }

    # For each commit, get full commit details to see other files changed
    co_changes: dict[str, int] = {}
    total_commits_analyzed = 0

    for commit in commits[:30]:  # Limit to 30 to reduce API calls
        try:
            full_commit = await client.get_commit(commit["sha"])
            files = full_commit.get("files", [])

            # Count co-changes
            for f in files:
                file_path = f.get("path", "")
                if file_path and file_path != path:
                    co_changes[file_path] = co_changes.get(file_path, 0) + 1

            total_commits_analyzed += 1

        except GitHubClientError:
            continue

    if total_commits_analyzed == 0:
        return {
            "success": False,
            "error": "Could not analyze any commits",
        }

    # Calculate coupling ratio and filter
    coupled_files: list[dict[str, Any]] = []
    for file_path, count in co_changes.items():
        coupling_ratio = count / total_commits_analyzed
        if coupling_ratio >= min_coupling:
            coupled_files.append(
                {
                    "path": file_path,
                    "co_change_count": count,
                    "coupling_ratio": round(coupling_ratio, 3),
                }
            )

    # Sort by coupling ratio
    coupled_files.sort(key=lambda x: x["coupling_ratio"], reverse=True)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "path": path,
        "total_commits_analyzed": total_commits_analyzed,
        "min_coupling_threshold": min_coupling,
        "coupled_files_count": len(coupled_files),
        "coupled_files": coupled_files[:20],  # Top 20
        "interpretation": (
            f"Files with coupling ratio >= {min_coupling} change together with {path} "
            f"at least {int(min_coupling * 100)}% of the time."
        ),
    }


async def _get_activity_summary(
    owner: str, repo: str, days: int, path: str | None, max_commits: int = 50
) -> dict[str, Any]:
    """Get aggregated summary of repository activity."""
    from datetime import datetime, timedelta

    client = GitHubClient(owner=owner, repo=repo, cache=_cache)

    # Calculate date threshold
    since_date = datetime.now() - timedelta(days=days)
    date_str = since_date.strftime("%Y-%m-%d")

    # Search for commits in date range
    query = f"committer-date:>{date_str}"
    if path:
        # Note: GitHub commit search doesn't support path filter, use list_commits instead
        commits = await client.list_commits(path=path, per_page=max_commits)
        # Filter by date manually
        commits = [c for c in commits if c["author"]["date"] and c["author"]["date"] >= date_str]
    else:
        result = await client.search_commits(query, per_page=max_commits)
        commits = result.get("items", [])

    if not commits:
        return {
            "success": True,
            "owner": owner,
            "repo": repo,
            "days": days,
            "path": path,
            "total_commits": 0,
            "message": f"No commits found in the last {days} days",
        }

    # Analyze commits
    by_type: dict[str, int] = {
        "bugfix": 0,
        "feature": 0,
        "refactor": 0,
        "docs": 0,
        "test": 0,
        "chore": 0,
        "other": 0,
    }
    by_author: dict[str, int] = {}

    type_keywords = {
        "bugfix": ["fix", "bug", "issue", "error", "crash", "patch"],
        "feature": ["add", "feat", "implement", "new", "introduce"],
        "refactor": ["refactor", "clean", "reorganize", "simplify"],
        "docs": ["doc", "readme", "comment", "typo"],
        "test": ["test", "spec", "coverage"],
        "chore": ["chore", "deps", "dependency", "upgrade", "bump", "ci", "build"],
    }

    for commit in commits:
        # Categorize by type
        msg_lower = commit.get("subject", "").lower()
        commit_type = "other"
        for type_name, keywords in type_keywords.items():
            if any(kw in msg_lower for kw in keywords):
                commit_type = type_name
                break
        by_type[commit_type] += 1

        # Count by author
        author = commit["author"]["name"]
        by_author[author] = by_author.get(author, 0) + 1

    # Sort authors by commit count
    top_authors = sorted(by_author.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "days": days,
        "path": path,
        "total_commits": len(commits),
        "commits_by_type": by_type,
        "top_contributors": [{"name": name, "commits": count} for name, count in top_authors],
        "summary": (
            f"In the last {days} days: {len(commits)} commits by {len(by_author)} contributors. "
            f"Bugfixes: {by_type['bugfix']}, Features: {by_type['feature']}, "
            f"Refactors: {by_type['refactor']}, Other: {by_type['other']}"
        ),
    }


# Explanation & Onboarding tool implementations
async def _explain_file(owner: str, repo: str, path: str, include_content: bool) -> dict[str, Any]:
    """Get comprehensive overview of a file."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)
    parser = CodeParser()

    # Get file content
    try:
        file_data = await client.get_file_contents(path)
    except GitHubClientError as e:
        return {"success": False, "error": f"Could not fetch file: {e}"}

    if file_data.get("type") != "file":
        return {"success": False, "error": f"Path is not a file: {path}"}

    content = file_data.get("content", "")
    file_size = file_data.get("size", 0)

    # Extract symbols if supported language
    symbols_info = None
    language = parser.detect_language(path)
    if language and content:
        try:
            symbols = parser.extract_symbols(content, language)
            symbols_info = {
                "language": language,
                "classes": [
                    {"name": s.qualified_name, "line": s.start_line}
                    for s in symbols
                    if s.type.value == "class"
                ],
                "functions": [
                    {"name": s.qualified_name, "line": s.start_line, "signature": s.signature}
                    for s in symbols
                    if s.type.value in ("function", "method")
                ][:20],  # Limit to 20
                "total_symbols": len(symbols),
            }
        except ParserError:
            pass

    # Get commit history
    commits = await client.list_commits(path=path, per_page=10)

    # Get top contributors
    author_counts: dict[str, int] = {}
    for commit in commits:
        author = commit["author"]["name"]
        author_counts[author] = author_counts.get(author, 0) + 1
    top_contributors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    # Recent changes
    recent_changes = []
    for commit in commits[:5]:
        recent_changes.append(
            {
                "sha": commit["short_sha"],
                "message": commit["subject"],
                "author": commit["author"]["name"],
                "date": commit["author"]["date"],
            }
        )

    # Build response
    result: dict[str, Any] = {
        "success": True,
        "owner": owner,
        "repo": repo,
        "path": path,
        "file_info": {
            "size_bytes": file_size,
            "html_url": file_data.get("html_url"),
        },
        "symbols": symbols_info,
        "history": {
            "total_commits": len(commits),
            "top_contributors": [
                {"name": name, "commits": count} for name, count in top_contributors
            ],
            "recent_changes": recent_changes,
        },
    }

    if include_content:
        # Truncate content if too large
        max_preview = 3000
        if len(content) > max_preview:
            result["content_preview"] = content[:max_preview] + "\n... (truncated)"
        else:
            result["content_preview"] = content

    return result


async def _list_github_tree(
    owner: str,
    repo: str,
    path_prefix: str | None,
    extension: str | None,
    max_depth: int | None,
    include_activity: bool = False,
) -> dict[str, Any]:
    """Get complete file tree of a repository."""
    client = GitHubClient(owner=owner, repo=repo, cache=_cache)

    try:
        tree_data = await client.get_tree()
    except GitHubClientError as e:
        return {"success": False, "error": f"Could not fetch tree: {e}"}

    entries = tree_data.get("entries", [])

    # Apply filters
    filtered_entries = []
    for entry in entries:
        path = entry["path"]

        # Filter by path prefix
        if path_prefix and not path.startswith(path_prefix):
            continue

        # Filter by extension
        if extension:
            if entry["type"] == "file" and not path.endswith(extension):
                continue

        # Filter by depth
        if max_depth is not None:
            depth = path.count("/")
            if depth > max_depth:
                continue

        filtered_entries.append(entry)

    # Organize into tree structure for readability
    dirs = [e for e in filtered_entries if e["type"] == "dir"]
    files = [e for e in filtered_entries if e["type"] == "file"]

    # Get file type statistics
    file_types: dict[str, int] = {}
    for f in files:
        ext = "." + f["path"].split(".")[-1] if "." in f["path"] else "(no ext)"
        file_types[ext] = file_types.get(ext, 0) + 1

    # Sort for consistent output
    dirs.sort(key=lambda x: x["path"])
    files.sort(key=lambda x: x["path"])

    result: dict[str, Any] = {
        "success": True,
        "owner": owner,
        "repo": repo,
        "filters": {
            "path_prefix": path_prefix,
            "extension": extension,
            "max_depth": max_depth,
        },
        "truncated": tree_data.get("truncated", False),
        "total_entries": len(filtered_entries),
        "total_dirs": len(dirs),
        "total_files": len(files),
        "file_types": dict(sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:15]),
        "directories": [d["path"] for d in dirs[:50]],
        "files": [{"path": f["path"], "size": f.get("size")} for f in files[:100]],
    }

    # Add activity info if requested
    if include_activity:
        # Get recent commits for this path
        commits = await client.list_commits(path=path_prefix, per_page=10)

        # Analyze activity
        author_counts: dict[str, int] = {}
        for commit in commits:
            author = commit["author"]["name"]
            author_counts[author] = author_counts.get(author, 0) + 1

        # Sort files by size to find key files
        files_by_size = sorted(files, key=lambda x: x.get("size", 0), reverse=True)

        result["activity"] = {
            "recent_commits": len(commits),
            "contributors": [
                {"name": name, "commits": count}
                for name, count in sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[
                    :5
                ]
            ],
        }
        result["key_files"] = [f["path"].split("/")[-1] for f in files_by_size[:5]]

    return result


async def _get_line_context(
    owner: str,
    repo: str,
    file_path: str,
    line_start: int,
    line_end: int | None,
    include_discussions: bool,
    history_depth: int = 1,
    ref: str | None = None,
) -> dict[str, Any]:
    """Gather all context about why specific lines exist.

    Aggregates: blame → commit → PR → issues → discussions.
    Returns structured data for LLM reasoning (no interpretation).

    Args:
        history_depth: Number of historical commits to analyze (default: 1).
            - 1: Just the most recent commit (fast, but might miss original introduction)
            - 5-10: Analyze recent history to find when code was actually added (recommended)
            - Higher values help find original context when recent commits only modified surrounding code
        ref: Git ref (branch, tag, or SHA) to analyze. Defaults to default branch.
    """
    line_end = line_end or line_start
    ref = ref or None  # Use None to get default branch from GitHub API

    result: dict[str, Any] = {
        "file_path": file_path,
        "line_range": [line_start, line_end],
        "current_content": None,
        "blame_commit": None,
        "historical_commits": [],  # NEW: Multiple commits if history_depth > 1
        "pull_request": None,
        "linked_issues": [],
        "context_availability": {
            "available": [],
            "missing": [],
            "confidence_hint": "low",
            "suggestions": [],
        },
    }

    try:
        client = GitHubClient(owner=owner, repo=repo, cache=_cache)

        # 1. Get current file content
        try:
            file_data = await client.get_file_contents(file_path, ref=ref)
            content = file_data.get("content", "")
            lines = content.split("\n")
            if line_start <= len(lines):
                result["current_content"] = "\n".join(lines[line_start - 1 : line_end])
        except Exception:
            pass

        # 2. Get commits for this file (proxy for blame)
        # Fetch more commits if history_depth > 1
        fetch_count = max(50, history_depth * 10)  # Fetch more to have options
        commits = await client.list_commits(path=file_path, per_page=fetch_count, sha=ref)

        if commits:
            # Use most recent commit as blame (simplified - proper blame needs diff analysis)
            blame_commit_data = commits[0]

            result["blame_commit"] = {
                "sha": blame_commit_data["sha"],
                "message": blame_commit_data["message"],
                "author": blame_commit_data["author"]["name"],
                "date": blame_commit_data["author"]["date"],
                "message_signals": _extract_message_signals(blame_commit_data["message"]),
            }

            # 2b. If history_depth > 1, fetch historical commits in batch
            if history_depth > 1 and len(commits) > 1:
                # Get SHAs for historical commits (skip first one, already have it)
                historical_shas = [c["sha"] for c in commits[1 : min(history_depth, len(commits))]]

                if historical_shas:
                    # Use batch operation for speed
                    historical_commits_dict = await client.get_commits_batch(historical_shas)

                    # Convert to list with metadata
                    for sha in historical_shas:
                        if sha in historical_commits_dict:
                            commit = historical_commits_dict[sha]
                            result["historical_commits"].append(
                                {
                                    "sha": sha,
                                    "message": _truncate(commit["message"], 300),
                                    "author": commit["author"]["name"],
                                    "date": commit["author"]["date"],
                                    "message_signals": _extract_message_signals(commit["message"]),
                                    "stats": commit["stats"],
                                }
                            )

            # 3. Find PR for this commit
            try:
                prs = await client.search_prs_for_commit(blame_commit_data["sha"])

                if prs and len(prs) > 0:
                    # search_prs_for_commit returns list of PR numbers (integers)
                    pr_number = prs[0]
                    pr_detail = await client.get_pull_request(pr_number)

                    result["pull_request"] = {
                        "number": pr_number,
                        "title": pr_detail.title,
                        "body": pr_detail.body or "",
                        "author": pr_detail.author.login if pr_detail.author else "",
                        "state": pr_detail.state,
                        "relevant_discussions": [],
                        "review_summary": None,
                    }

                    # 4. Get PR discussions if requested
                    if include_discussions:
                        # Combine comments and review comments
                        comments = await client.get_pr_comments(pr_number)
                        review_comments = await client.get_pr_review_comments(pr_number)

                        # Filter to relevant discussions
                        all_comments = comments + review_comments
                        relevant = _filter_relevant_discussions(all_comments)
                        result["pull_request"]["relevant_discussions"] = relevant[:5]

                        # Get review summary
                        reviews = await client.get_pr_reviews(pr_number)
                        result["pull_request"]["review_summary"] = _summarize_reviews(reviews)

                    # 5. Find linked issues from multiple sources:
                    # a. Text-based: Parse PR title, body, and commit message
                    issue_refs_text = _extract_issue_references(
                        (pr_detail.title or "")
                        + " "
                        + (pr_detail.body or "")
                        + " "
                        + blame_commit_data["message"]
                    )
                    # b. API-based: Get issues linked via GitHub's Development sidebar
                    try:
                        issue_refs_api = await client.get_pr_linked_issues(pr_number)
                    except Exception:
                        issue_refs_api = []

                    # Combine and deduplicate, excluding the PR number itself
                    issue_refs = list(set(issue_refs_text + issue_refs_api))
                    issue_refs = [n for n in issue_refs if n != pr_number]

                    for issue_num in issue_refs[:3]:
                        try:
                            issue = await client.get_issue(issue_num)
                            result["linked_issues"].append(
                                {
                                    "number": issue_num,
                                    "title": issue.title,
                                    "body": issue.body[:500] if issue.body else None,
                                    "author": issue.author.login if issue.author else None,
                                    "labels": [label.name for label in issue.labels],
                                    "state": issue.state,
                                    "html_url": issue.html_url,
                                }
                            )
                        except Exception:
                            pass
            except Exception:
                # If PR search fails, continue without PR context
                pass

        # Compute context availability
        result["context_availability"] = _compute_context_availability(result)

    except Exception as e:
        result["error"] = str(e)
        result["context_availability"]["missing"].append("api_error")

    return result


def _extract_message_signals(message: str) -> list[str]:
    """Extract signals from commit message."""
    signals = []
    message_lower = message.lower()

    if any(word in message_lower for word in ["fix", "bug", "issue"]):
        signals.append("contains_fix_keywords")
    if any(word in message_lower for word in ["add", "feature", "implement"]):
        signals.append("contains_feature_keywords")
    if len(message) < 20:
        signals.append("short_message")
    if "\n\n" in message:
        signals.append("has_detailed_body")

    return signals


def _extract_function_names(content: str) -> set[str]:
    """Extract likely function/method names from code content."""
    import re

    names = set()

    # Match patterns like: .def("FunctionName", or def function_name( or function FunctionName(
    patterns_to_match = [
        r'\.def\s*\(\s*["\'](\w+)["\']',  # pybind11: .def("Name"
        r"def\s+(\w+)\s*\(",  # Python: def name(
        r"function\s+(\w+)\s*\(",  # JS: function name(
        r"(?:void|int|bool|auto)\s+(\w+)\s*\(",  # C++: type name(
    ]

    for pattern in patterns_to_match:
        for match in re.finditer(pattern, content):
            names.add(match.group(1))

    return names


def _detect_patterns(
    code_sections: list[dict[str, Any]],
    nearby_context: dict[str, Any] | None,
    pr_info: dict[str, Any] | None,
    linked_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect common patterns that may inform quick answers."""
    patterns = []

    # Check if code is commented
    is_commented = any(s.get("is_currently_commented") for s in code_sections)

    # Get all content from sections
    all_section_content = "\n".join(s.get("content", "") for s in code_sections)

    # Pattern 1: Commented code with active alternative nearby
    if is_commented and nearby_context:
        after_lines = nearby_context.get("after", {}).get("content", "")
        if after_lines:
            # Check if lines after are NOT comments (i.e., active code)
            after_stripped = [line.strip() for line in after_lines.split("\n") if line.strip()]
            if after_stripped and not all(
                line.startswith(("//", "#", "/*", "*", "<!--")) for line in after_stripped
            ):
                # Extract function names from commented code
                commented_functions = _extract_function_names(all_section_content)
                active_functions = _extract_function_names(after_lines)

                # Check if same function appears in both
                shared_functions = commented_functions & active_functions

                if shared_functions:
                    func_list = ", ".join(sorted(shared_functions))
                    patterns.append(
                        {
                            "type": "commented_alternative_same_function",
                            "message": f"Commented code for '{func_list}' has ACTIVE binding immediately below",
                            "hint": f"The function '{func_list}' IS already bound. This commented code is an UNUSED ALTERNATIVE, not missing functionality. The active binding works.",
                        }
                    )
                else:
                    patterns.append(
                        {
                            "type": "commented_with_active_alternative",
                            "message": "Commented code with active code immediately below",
                            "hint": "This may be an unused alternative to the active implementation below",
                        }
                    )

    # Pattern 2: TODO/FIXME/BUG markers
    all_content = "\n".join(s.get("content", "") for s in code_sections).upper()
    if any(marker in all_content for marker in ["TODO", "FIXME", "XXX", "HACK", "BUG"]):
        patterns.append(
            {
                "type": "todo_or_bug_marker",
                "message": "Code contains TODO/FIXME/BUG marker",
                "hint": "Check if the referenced issue is resolved or if this is stale",
            }
        )

        # Pattern 2b: TODO exists but PR claims to "fix" something
        if pr_info:
            pr_title = (pr_info.get("title") or "").lower()
            if any(kw in pr_title for kw in ["fix", "resolve", "close"]):
                patterns.append(
                    {
                        "type": "fix_pr_with_persistent_todo",
                        "message": "PR claims 'fix' but TODO/FIXME still exists",
                        "hint": "The TODO may be stale or the fix was partial",
                    }
                )

    # Pattern 3: Simple documentation comment
    if is_commented and not patterns:
        # All content is comments and no special markers
        if not any(marker in all_content for marker in ["TODO", "FIXME", "XXX"]):
            patterns.append(
                {
                    "type": "documentation_comment",
                    "message": "This appears to be a documentation comment",
                    "hint": "May just be explaining the code below",
                }
            )

    return patterns


def _get_nearby_context(
    repo: "GitRepo",
    file_path: str,
    line_start: int,
    line_end: int,
    context_lines: int = 10,
) -> dict[str, Any]:
    """Get lines before and after the selection for context detection."""
    try:
        # Get file content from working directory
        full_path = repo.path / file_path
        if not full_path.exists():
            return {}
        full_content = full_path.read_text(encoding="utf-8", errors="replace")
        if not full_content:
            return {}

        lines = full_content.split("\n")
        total_lines = len(lines)

        # Get lines before (but not before line 1)
        before_start = max(0, line_start - context_lines - 1)
        before_end = line_start - 1
        before_lines = lines[before_start:before_end] if before_end > before_start else []

        # Get lines after (but not past end of file)
        after_start = line_end
        after_end = min(total_lines, line_end + context_lines)
        after_lines = lines[after_start:after_end] if after_end > after_start else []

        return {
            "before": {
                "lines": [before_start + 1, before_end] if before_lines else None,
                "content": "\n".join(before_lines) if before_lines else None,
            },
            "after": {
                "lines": [after_start + 1, after_end] if after_lines else None,
                "content": "\n".join(after_lines) if after_lines else None,
            },
        }
    except Exception:
        return {}


def _generate_quick_answer(
    code_sections: list[dict[str, Any]],
    patterns: list[dict[str, Any]],
    pr_info: dict[str, Any] | None,
    linked_issues: list[dict[str, Any]],
) -> str | None:
    """Generate a TL;DR based on detected patterns.

    Returns None if the situation requires deeper investigation.
    """
    pattern_types = {p["type"] for p in patterns}
    pattern_by_type = {p["type"]: p for p in patterns}

    # BEST CASE: Commented code with SAME function active below
    if "commented_alternative_same_function" in pattern_types:
        pattern = pattern_by_type["commented_alternative_same_function"]
        # Extract function name from the message
        return f"This is an UNUSED ALTERNATIVE implementation. {pattern['hint']}"

    # Commented code with active alternative - clear case
    if "commented_with_active_alternative" in pattern_types:
        return "This is commented-out code with an active implementation below. Likely an unused alternative or documentation of a different approach."

    # Simple documentation comment
    if "documentation_comment" in pattern_types:
        return "This appears to be a documentation comment explaining nearby code."

    # Fix PR with persistent TODO - interesting case
    if "fix_pr_with_persistent_todo" in pattern_types:
        return "A PR claimed to fix this, but a TODO/FIXME marker persists. The TODO may be stale or the fix was partial."

    # Bug fix with linked issue
    if pr_info and linked_issues:
        pr_title = (pr_info.get("title") or "").lower()
        if any(kw in pr_title for kw in ["fix", "bug"]):
            issue = linked_issues[0]
            return f"Bug fix for {issue.get('title', 'an issue')} (Issue #{issue.get('number')})."

    return None  # No quick answer - needs investigation


def _calculate_confidence(
    code_sections: list[dict[str, Any]],
    pr_info: dict[str, Any] | None,
    linked_issues: list[dict[str, Any]],
    patterns: list[dict[str, Any]],
    nearby_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Calculate confidence score with specific signals."""
    score = 0
    signals = []

    # Positive signals
    if pr_info:
        score += 25
        signals.append("✓ Found associated PR")
    if linked_issues:
        score += 20
        signals.append("✓ Found linked issues")

    # Check if origins were found for all sections
    sections_with_origins = sum(1 for s in code_sections if s.get("origins"))
    if sections_with_origins == len(code_sections) and code_sections:
        score += 25
        signals.append("✓ Found true origin via pickaxe")
    elif sections_with_origins > 0:
        score += 15
        signals.append(f"⚠ Found origin for {sections_with_origins}/{len(code_sections)} sections")

    if nearby_context and (nearby_context.get("before") or nearby_context.get("after")):
        score += 10
        signals.append("✓ Nearby context available")

    # Negative/warning signals from patterns
    for p in patterns:
        if p["type"] == "todo_or_bug_marker":
            signals.append("⚠ Contains TODO/FIXME marker - may need verification")
        if p["type"] == "fix_pr_with_persistent_todo":
            score -= 10
            signals.append("⚠ PR claims 'fix' but TODO persists - conflicting signals")

    # Determine level
    level = "high" if score >= 60 else "medium" if score >= 30 else "low"

    return {
        "score": min(100, max(0, score)),
        "level": level,
        "signals": signals,
    }


def _filter_relevant_discussions(
    comments: list[dict[str, Any]] | list[Comment],
) -> list[dict[str, Any]]:
    """Filter to discussions indicating decisions/alternatives."""
    decision_keywords = [
        "instead",
        "alternative",
        "could",
        "should",
        "consider",
        "why",
        "because",
        "decided",
        "chose",
        "trade-off",
    ]

    relevant: list[dict[str, Any]] = []
    for comment in comments:
        # Handle both Comment objects and dicts
        if isinstance(comment, Comment):
            body = (comment.body or "").lower()
            author = comment.author.login if comment.author else ""
            comment_body = comment.body or ""
            has_review_id = comment.commit_sha is not None
            html_url = ""
        else:
            body = (comment.get("body") or "").lower()
            author = comment.get("user", {}).get("login", "")
            comment_body = comment.get("body", "")
            has_review_id = "pull_request_review_id" in comment
            html_url = comment.get("html_url", "")

        if any(kw in body for kw in decision_keywords):
            relevant.append(
                {
                    "author": author,
                    "body": comment_body[:500],
                    "type": "review_comment" if has_review_id else "pr_comment",
                    "url": html_url,
                }
            )

    return relevant


def _extract_issue_references(text: str) -> list[int]:
    """Extract issue numbers from text.

    Detects multiple patterns:
    - #123 (standard GitHub reference)
    - fixes #123, closes #123, resolves #123
    - issue 123, issue #123
    - Leading number in PR title like "123 Fix the bug"
    """
    import re

    issues: set[int] = set()

    # Standard #number references
    for m in re.findall(r"#(\d+)", text):
        issues.add(int(m))

    # "fixes/closes/resolves issue 123" or "fixes/closes/resolves 123"
    for m in re.findall(
        r"(?:fix(?:es)?|close[sd]?|resolve[sd]?)\s+(?:issue\s+)?#?(\d+)", text, re.I
    ):
        issues.add(int(m))

    # "issue 123" or "issue #123"
    for m in re.findall(r"issue\s+#?(\d+)", text, re.I):
        issues.add(int(m))

    # Leading number at start of text (common in PR titles like "123 Fix bug")
    leading = re.match(r"^(\d+)\s+\w", text.strip())
    if leading:
        issues.add(int(leading.group(1)))

    return list(issues)


def _summarize_reviews(reviews: list) -> dict:
    """Summarize PR reviews."""
    approved_by = []
    changes_requested_by = []

    for review in reviews:
        state = getattr(review, "state", "")
        author = getattr(review.user, "login", "") if review.user else ""

        if state == "APPROVED":
            approved_by.append(author)
        elif state == "CHANGES_REQUESTED":
            changes_requested_by.append(author)

    return {
        "approved_by": list(set(approved_by)),
        "changes_requested_by": list(set(changes_requested_by)),
        "total_reviews": len(reviews),
    }


def _compute_context_availability(context: dict) -> dict:
    """Compute what context is available vs missing."""
    available = []
    missing = []
    suggestions = []

    if context.get("current_content"):
        available.append("file_content")

    if context.get("blame_commit"):
        commit = context["blame_commit"]
        available.append("commit")

        if "has_detailed_body" in commit.get("message_signals", []):
            available.append("detailed_commit_message")
        if "short_message" in commit.get("message_signals", []):
            missing.append("meaningful_commit_message")
            suggestions.append("Commit message is generic - context may be limited")
    else:
        missing.append("blame_commit")

    # Check for historical commits
    if context.get("historical_commits") and len(context["historical_commits"]) > 0:
        available.append("historical_commits")
        suggestions.append(
            f"Found {len(context['historical_commits'])} historical commits for deeper context"
        )

    if context.get("pull_request"):
        pr = context["pull_request"]
        available.append("pull_request")

        if pr.get("body"):
            available.append("pr_description")
        else:
            missing.append("pr_description")

        if pr.get("relevant_discussions"):
            available.append("pr_discussions")
        else:
            missing.append("pr_discussions")
    else:
        missing.append("pull_request")
        suggestions.append("No PR found - commit may have been pushed directly")

    if context.get("linked_issues"):
        available.append("linked_issues")
    else:
        missing.append("linked_issues")

    # Compute confidence
    confidence_score = len(available) - len(missing)
    if confidence_score >= 5:
        confidence = "high"
    elif confidence_score >= 2:
        confidence = "medium"
    elif confidence_score >= 0:
        confidence = "low"
    else:
        confidence = "very_low"

    return {
        "available": available,
        "missing": missing,
        "confidence_hint": confidence,
        "suggestions": suggestions,
    }


async def _run() -> None:
    """Run the MCP server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Entry point for the MCP server."""
    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
