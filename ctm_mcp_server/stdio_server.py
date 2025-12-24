"""
Codebase Time Machine - MCP Protocol Server

This module implements the MCP (Model Context Protocol) server using stdio transport.
It exposes all CTM tools to LLM clients like Claude.
"""

import json
import re
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ctm_mcp_server.data.git_repo import GitRepo, GitRepoError
from ctm_mcp_server.data.github_client import GitHubClient, GitHubClientError
from ctm_mcp_server.models.result_models import IntentType
from ctm_mcp_server.parsing.parser import CodeParser, ParserError

# Create the MCP server instance
server = Server("codebase-time-machine")


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
            description="Enhanced git blame that shows not just who changed each line, but links to PRs, issues, and explains the intent.",
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
            name="get_code_context",
            description="Trace the full decision chain for code: file commits → PRs → linked issues. Answers 'Why does this code exist?' by aggregating all context.",
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
                        "description": "Maximum commits to analyze (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["owner", "repo", "path"],
            },
        ),
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
            description="Get aggregated summary of repository activity: commits by type (bugfix/feature/etc), top contributors, most changed files, filtered by time range.",
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
                        "description": "Optional: filter to specific path/directory",
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
            description="Get the complete file tree of a GitHub repository in one fast API call. Essential for understanding codebase structure. Can filter by path prefix and file extension.",
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
                },
                "required": ["owner", "repo"],
            },
        ),
        Tool(
            name="explain_directory",
            description="Get an overview of a directory: structure, file types, key files, recent activity, and purpose. Useful for understanding codebase layout.",
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
                        "description": "Directory path relative to repo root (use '' or '.' for root)",
                        "default": "",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How deep to explore subdirectories (default: 2)",
                        "default": 2,
                    },
                },
                "required": ["owner", "repo"],
            },
        ),
        Tool(
            name="get_recent_activity",
            description="Get recent commit activity for a file or directory. Shows what changed recently, who made changes, and links to PRs.",
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
                        "description": "File or directory path (optional, defaults to entire repo)",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 14)",
                        "default": 14,
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "Maximum commits to return (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["owner", "repo"],
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
        elif name == "explain_commit":
            result = await _explain_commit(arguments["repo_path"], arguments["sha"])
        elif name == "blame_with_context":
            result = await _blame_with_context(
                arguments["repo_path"],
                arguments["file_path"],
                arguments.get("start_line"),
                arguments.get("end_line"),
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
        elif name == "get_code_context":
            result = await _get_code_context(
                arguments["owner"],
                arguments["repo"],
                arguments["path"],
                arguments.get("max_commits", 10),
            )
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
            )
        elif name == "explain_directory":
            result = await _explain_directory(
                arguments["owner"],
                arguments["repo"],
                arguments.get("path", ""),
                arguments.get("depth", 2),
            )
        elif name == "get_recent_activity":
            result = await _get_recent_activity(
                arguments["owner"],
                arguments["repo"],
                arguments.get("path"),
                arguments.get("days", 14),
                arguments.get("max_commits", 20),
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
    repo = GitRepo(repo_path)
    commit = repo.get_commit(sha)

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


# GitHub API tool implementations
async def _get_github_repo(owner: str, repo: str) -> dict[str, Any]:
    """Get GitHub repository info via API."""
    client = GitHubClient(owner=owner, repo=repo)
    info = await client.get_repo_info()

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        **info,
    }


async def _get_github_branches(owner: str, repo: str) -> dict[str, Any]:
    """Get GitHub repository branches via API."""
    client = GitHubClient(owner=owner, repo=repo)
    branches = await client.get_branches()

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "branches": branches,
    }


async def _get_github_commit(owner: str, repo: str, sha: str) -> dict[str, Any]:
    """Get GitHub commit details via API (optimized for token efficiency)."""
    client = GitHubClient(owner=owner, repo=repo)
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


async def _get_github_file_history(
    owner: str, repo: str, path: str, max_commits: int
) -> dict[str, Any]:
    """Get file commit history via GitHub API."""
    client = GitHubClient(owner=owner, repo=repo)
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
    client = GitHubClient(owner=owner, repo=repo)
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
    client = GitHubClient(owner=owner, repo=repo)
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
    client = GitHubClient(owner=owner, repo=repo)
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
    """Search for PRs containing a commit via GitHub API."""
    client = GitHubClient(owner=owner, repo=repo)
    pr_numbers = await client.search_prs_for_commit(sha)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "sha": sha,
        "pr_numbers": pr_numbers,
        "total_found": len(pr_numbers),
    }


# Search tool implementations
async def _search_github_code(owner: str, repo: str, query: str, per_page: int) -> dict[str, Any]:
    """Search for code in a GitHub repository."""
    client = GitHubClient(owner=owner, repo=repo)
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
    client = GitHubClient(owner=owner, repo=repo)
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
    client = GitHubClient(owner=owner, repo=repo)
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
    client = GitHubClient(owner=owner, repo=repo)
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
async def _get_code_context(owner: str, repo: str, path: str, max_commits: int) -> dict[str, Any]:
    """Get full decision chain: commits → PRs → issues for a file."""
    client = GitHubClient(owner=owner, repo=repo)

    # Get recent commits for this file
    commits = await client.list_commits(path=path, per_page=max_commits)

    if not commits:
        return {
            "success": False,
            "error": f"No commits found for file: {path}",
        }

    # Build context chain
    context_chain: list[dict[str, Any]] = []
    prs_seen: set[int] = set()
    issues_seen: set[int] = set()

    for commit in commits:
        commit_context: dict[str, Any] = {
            "commit": {
                "sha": commit["short_sha"],
                "message": commit["subject"],
                "author": commit["author"]["name"],
                "date": commit["author"]["date"],
                "html_url": commit.get("html_url"),
            },
            "prs": [],
            "issues": [],
        }

        # Find PRs for this commit
        try:
            pr_numbers = await client.search_prs_for_commit(commit["sha"])
            for pr_num in pr_numbers[:3]:  # Limit to 3 PRs per commit
                if pr_num in prs_seen:
                    continue
                prs_seen.add(pr_num)

                try:
                    pr = await client.get_pull_request(pr_num)
                    pr_info = {
                        "number": pr.number,
                        "title": pr.title,
                        "state": pr.state.value,
                        "author": pr.author.login,
                        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                        "html_url": pr.html_url,
                        "linked_issues": pr.linked_issues,
                    }
                    commit_context["prs"].append(pr_info)

                    # Fetch linked issues
                    for issue_num in pr.linked_issues:
                        if issue_num in issues_seen:
                            continue
                        issues_seen.add(issue_num)

                        try:
                            issue = await client.get_issue(issue_num)
                            issue_info = {
                                "number": issue.number,
                                "title": issue.title,
                                "state": issue.state.value,
                                "author": issue.author.login,
                                "labels": [lbl.name for lbl in issue.labels],
                                "html_url": issue.html_url,
                            }
                            commit_context["issues"].append(issue_info)
                        except GitHubClientError:
                            pass

                except GitHubClientError:
                    pass

        except GitHubClientError:
            pass

        context_chain.append(commit_context)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "path": path,
        "total_commits": len(commits),
        "total_prs_found": len(prs_seen),
        "total_issues_found": len(issues_seen),
        "context_chain": context_chain,
    }


async def _get_code_owners(owner: str, repo: str, path: str, max_commits: int) -> dict[str, Any]:
    """Find who knows this code best by analyzing commit history."""
    client = GitHubClient(owner=owner, repo=repo)

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
    client = GitHubClient(owner=owner, repo=repo)

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
    coupled_files = []
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
    owner: str, repo: str, days: int, path: str | None
) -> dict[str, Any]:
    """Get aggregated summary of repository activity."""
    from datetime import datetime, timedelta

    client = GitHubClient(owner=owner, repo=repo)

    # Calculate date threshold
    since_date = datetime.now() - timedelta(days=days)
    date_str = since_date.strftime("%Y-%m-%d")

    # Search for commits in date range
    query = f"committer-date:>{date_str}"
    if path:
        # Note: GitHub commit search doesn't support path filter, use list_commits instead
        commits = await client.list_commits(path=path, per_page=100)
        # Filter by date manually
        commits = [c for c in commits if c["author"]["date"] and c["author"]["date"] >= date_str]
    else:
        result = await client.search_commits(query, per_page=100)
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
    client = GitHubClient(owner=owner, repo=repo)
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
                ][
                    :20
                ],  # Limit to 20
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
) -> dict[str, Any]:
    """Get complete file tree of a repository."""
    client = GitHubClient(owner=owner, repo=repo)

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

    return {
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


async def _explain_directory(owner: str, repo: str, path: str, _depth: int) -> dict[str, Any]:
    """Get overview of a directory structure."""
    client = GitHubClient(owner=owner, repo=repo)

    # Normalize path
    if path in (".", ""):
        path = ""

    # Get directory contents using get_file_contents (works for dirs too)
    try:
        # For root, use empty string or "."
        dir_data = await client.get_file_contents(path if path else ".")
    except GitHubClientError as e:
        return {"success": False, "error": f"Could not fetch directory: {e}"}

    # Check if it's a directory
    if dir_data.get("type") != "directory":
        return {"success": False, "error": f"Path is not a directory: {path}"}

    contents = dir_data.get("entries", [])

    # Categorize contents
    dirs: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    file_types: dict[str, int] = {}

    for item in contents:
        if item["type"] == "dir":
            dirs.append(
                {
                    "name": item["name"],
                    "path": item["path"],
                }
            )
        else:
            files.append(
                {
                    "name": item["name"],
                    "path": item["path"],
                    "size": item.get("size", 0),
                }
            )
            # Count file types
            ext = "." + item["name"].split(".")[-1] if "." in item["name"] else "(no ext)"
            file_types[ext] = file_types.get(ext, 0) + 1

    # Sort files by size to find key files
    files.sort(key=lambda x: x.get("size", 0), reverse=True)

    # Get recent commits for this path
    commits = await client.list_commits(path=path if path else None, per_page=10)

    # Analyze activity
    author_counts: dict[str, int] = {}
    for commit in commits:
        author = commit["author"]["name"]
        author_counts[author] = author_counts.get(author, 0) + 1

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "path": path or "(root)",
        "structure": {
            "total_dirs": len(dirs),
            "total_files": len(files),
            "directories": dirs[:20],  # Limit
            "files": files[:30],  # Limit
            "file_types": dict(sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:10]),
        },
        "activity": {
            "recent_commits": len(commits),
            "contributors": [
                {"name": name, "commits": count}
                for name, count in sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[
                    :5
                ]
            ],
        },
        "key_files": [f["name"] for f in files[:5]],  # Largest files are often important
    }


async def _get_recent_activity(
    owner: str, repo: str, path: str | None, days: int, max_commits: int
) -> dict[str, Any]:
    """Get recent commit activity for a path."""
    from datetime import datetime, timedelta

    client = GitHubClient(owner=owner, repo=repo)

    # Calculate date threshold
    since_date = datetime.now() - timedelta(days=days)
    date_str = since_date.strftime("%Y-%m-%d")

    # Get commits
    commits = await client.list_commits(path=path, per_page=max_commits)

    # Filter by date
    recent_commits = [c for c in commits if c["author"]["date"] and c["author"]["date"] >= date_str]

    if not recent_commits:
        return {
            "success": True,
            "owner": owner,
            "repo": repo,
            "path": path,
            "days": days,
            "total_commits": 0,
            "message": f"No commits in the last {days} days",
        }

    # Build activity list with PR links
    activities: list[dict[str, Any]] = []
    for commit in recent_commits:
        activity: dict[str, Any] = {
            "sha": commit["short_sha"],
            "message": commit["subject"],
            "author": commit["author"]["name"],
            "date": commit["author"]["date"],
            "html_url": commit.get("html_url"),
        }

        # Try to find associated PR
        try:
            pr_numbers = await client.search_prs_for_commit(commit["sha"])
            if pr_numbers:
                activity["pr_number"] = pr_numbers[0]
        except GitHubClientError:
            pass

        activities.append(activity)

    # Aggregate by author
    by_author: dict[str, int] = {}
    for commit in recent_commits:
        author = commit["author"]["name"]
        by_author[author] = by_author.get(author, 0) + 1

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "path": path,
        "days": days,
        "total_commits": len(recent_commits),
        "activities": activities,
        "by_author": [
            {"name": name, "commits": count}
            for name, count in sorted(by_author.items(), key=lambda x: x[1], reverse=True)
        ],
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
