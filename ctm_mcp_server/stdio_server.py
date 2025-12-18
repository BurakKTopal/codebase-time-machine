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
        else:
            result = {"success": False, "error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except GitRepoError as e:
        error_result = {"success": False, "error": str(e)}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]
    except GitHubClientError as e:
        error_result = {"success": False, "error": f"GitHub API error: {e}"}
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
    """Get GitHub commit details via API."""
    client = GitHubClient(owner=owner, repo=repo)
    commit = await client.get_commit(sha)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        **commit,
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


async def _get_github_file(owner: str, repo: str, path: str, ref: str | None) -> dict[str, Any]:
    """Get file contents via GitHub API."""
    client = GitHubClient(owner=owner, repo=repo)
    file_data = await client.get_file_contents(path, ref=ref)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "ref": ref,
        **file_data,
    }


async def _get_pr(owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    """Get PR details via GitHub API."""
    client = GitHubClient(owner=owner, repo=repo)
    pr = await client.get_pull_request(pr_number)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "pr": {
            "number": pr.number,
            "title": pr.title,
            "body": pr.body,
            "state": pr.state.value,
            "author": pr.author.login,
            "labels": [lbl.name for lbl in pr.labels],
            "assignees": [usr.login for usr in pr.assignees],
            "reviewers": [usr.login for usr in pr.reviewers],
            "created_at": pr.created_at.isoformat() if pr.created_at else None,
            "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
            "closed_at": pr.closed_at.isoformat() if pr.closed_at else None,
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
            "merged_by": pr.merged_by.login if pr.merged_by else None,
            "head_ref": pr.head_ref,
            "base_ref": pr.base_ref,
            "head_sha": pr.head_sha,
            "base_sha": pr.base_sha,
            "merge_commit_sha": pr.merge_commit_sha,
            "is_merged": pr.is_merged,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": pr.changed_files,
            "commits_count": pr.commits_count,
            "linked_issues": pr.linked_issues,
            "html_url": pr.html_url,
            "comments": [
                {
                    "id": c.id,
                    "author": c.author.login,
                    "body": c.body,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "path": c.path,
                    "line": c.line,
                }
                for c in pr.comments
            ],
            "reviews": [
                {
                    "id": r.id,
                    "author": r.author.login,
                    "state": r.state.value,
                    "body": r.body,
                    "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                }
                for r in pr.reviews
            ],
            "review_comments": [
                {
                    "id": c.id,
                    "author": c.author.login,
                    "body": c.body,
                    "path": c.path,
                    "line": c.line,
                    "commit_sha": c.commit_sha,
                }
                for c in pr.review_comments
            ],
        },
    }


async def _get_issue(owner: str, repo: str, issue_number: int) -> dict[str, Any]:
    """Get issue details via GitHub API."""
    client = GitHubClient(owner=owner, repo=repo)
    issue = await client.get_issue(issue_number)

    return {
        "success": True,
        "owner": owner,
        "repo": repo,
        "issue": {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "state": issue.state.value,
            "author": issue.author.login,
            "labels": [lbl.name for lbl in issue.labels],
            "assignees": [usr.login for usr in issue.assignees],
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
            "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
            "comments_count": issue.comments_count,
            "html_url": issue.html_url,
            "comments": [
                {
                    "id": c.id,
                    "author": c.author.login,
                    "body": c.body,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in issue.comments
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
