"""
Codebase Time Machine - MCP Protocol Server

This module implements the MCP (Model Context Protocol) server using stdio transport.
It exposes all CTM tools to LLM clients like Claude.
"""

import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

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
                        "description": "Start line number (1-indexed)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line number (1-indexed)",
                    },
                },
                "required": ["repo_path", "file_path"],
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
            result = await _list_branches(arguments["repo_path"])
        elif name == "get_commit":
            result = await _get_commit(arguments["repo_path"], arguments["sha"])
        elif name == "trace_file_history":
            result = await _trace_file_history(
                arguments["repo_path"],
                arguments["file_path"],
                arguments.get("max_commits", 50),
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
        else:
            result = {"success": False, "error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


# Placeholder implementations - will be replaced with actual implementations
async def _get_repo_info(repo_path: str) -> dict[str, Any]:
    """Get repository information."""
    return {
        "success": True,
        "message": "Tool not yet implemented - this is a placeholder",
        "tool": "get_repo_info",
        "repo_path": repo_path,
    }


async def _list_branches(repo_path: str) -> dict[str, Any]:
    """List all branches."""
    return {
        "success": True,
        "message": "Tool not yet implemented - this is a placeholder",
        "tool": "list_branches",
        "repo_path": repo_path,
    }


async def _get_commit(repo_path: str, sha: str) -> dict[str, Any]:
    """Get commit details."""
    return {
        "success": True,
        "message": "Tool not yet implemented - this is a placeholder",
        "tool": "get_commit",
        "repo_path": repo_path,
        "sha": sha,
    }


async def _trace_file_history(repo_path: str, file_path: str, max_commits: int) -> dict[str, Any]:
    """Trace file history."""
    return {
        "success": True,
        "message": "Tool not yet implemented - this is a placeholder",
        "tool": "trace_file_history",
        "repo_path": repo_path,
        "file_path": file_path,
        "max_commits": max_commits,
    }


async def _explain_commit(repo_path: str, sha: str) -> dict[str, Any]:
    """Explain commit intent."""
    return {
        "success": True,
        "message": "Tool not yet implemented - this is a placeholder",
        "tool": "explain_commit",
        "repo_path": repo_path,
        "sha": sha,
    }


async def _blame_with_context(
    repo_path: str,
    file_path: str,
    start_line: int | None,
    end_line: int | None,
) -> dict[str, Any]:
    """Enhanced blame with context."""
    return {
        "success": True,
        "message": "Tool not yet implemented - this is a placeholder",
        "tool": "blame_with_context",
        "repo_path": repo_path,
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
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
