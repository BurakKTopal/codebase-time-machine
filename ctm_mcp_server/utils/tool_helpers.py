"""Shared utilities for CTM tool implementations."""

from typing import Any

from ctm_mcp_server.data.git_repo import GitRepo
from ctm_mcp_server.data.github_client import GitHubClient, GitHubClientError
from ctm_mcp_server.models.github_models import Comment


def truncate(text: str | None, max_len: int = 500) -> str | None:
    """Truncate text to max_len with ellipsis."""
    if not text or len(text) <= max_len:
        return text
    return text[:max_len] + "... [truncated]"


def extract_message_signals(message: str) -> list[str]:
    """Extract categorization signals from commit message."""
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


def filter_relevant_discussions(
    comments: list[dict[str, Any]] | list[Comment],
) -> list[dict[str, Any]]:
    """Filter PR/issue comments for decision-making discussions."""
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
            has_review_id = comment.commit_sha is not None  # Review comments have commit_sha
            html_url = ""  # Comment model doesn't have html_url
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


async def build_context_chain(
    client: GitHubClient,
    commit_sha: str,
    include_discussions: bool = True,
    max_prs_per_commit: int = 3,
    max_issues_per_pr: int = 3,
) -> dict[str, Any]:
    """Build commit → PR → issue context chain.

    Shared by get_line_context and get_code_context.
    """
    import re

    result: dict[str, Any] = {
        "pull_request": None,
        "linked_issues": [],
        "discussions": [],
    }

    try:
        pr_numbers = await client.search_prs_for_commit(commit_sha)

        if pr_numbers and len(pr_numbers) > 0:
            pr_number = (
                pr_numbers[0]["number"] if isinstance(pr_numbers[0], dict) else pr_numbers[0]
            )
            pr_detail = await client.get_pull_request(pr_number)

            result["pull_request"] = {
                "number": pr_number,
                "title": pr_detail.title,
                "body": pr_detail.body or "",
                "author": pr_detail.author.login if pr_detail.author else "",
                "state": pr_detail.state,
                "merged_at": (pr_detail.merged_at.isoformat() if pr_detail.merged_at else None),
                "html_url": pr_detail.html_url,
            }

            pr_body = pr_detail.body or ""
            issue_refs = re.findall(
                r"(?:fix(?:es)?|close(?:s)?|resolve(?:s)?)\s+#(\d+)", pr_body, re.IGNORECASE
            )
            issue_refs += re.findall(r"(?:^|\s)#(\d+)", pr_body)
            unique_issues = list(set(issue_refs))[:max_issues_per_pr]

            linked_issues: list[dict[str, Any]] = result["linked_issues"]
            for issue_num_str in unique_issues:
                try:
                    issue_num = int(issue_num_str)
                    issue = await client.get_issue(issue_num)

                    linked_issues.append(
                        {
                            "number": issue.number,
                            "title": issue.title,
                            "body": truncate(issue.body, 1000),
                            "author": issue.author.login if issue.author else "",
                            "state": issue.state,
                            "created_at": issue.created_at.isoformat(),
                            "html_url": issue.html_url,
                        }
                    )
                except Exception:
                    pass

            if include_discussions:
                try:
                    pr_comments = await client.get_pr_comments(pr_number)
                    review_comments = await client.get_pr_review_comments(pr_number)
                    all_comments = pr_comments + review_comments
                    result["discussions"] = filter_relevant_discussions(all_comments)
                except Exception:
                    pass

    except GitHubClientError:
        pass

    return result


def detect_github_remote(repo: GitRepo) -> tuple[str, str] | None:
    """Detect GitHub remote from local repo.

    Args:
        repo: GitRepo instance

    Returns:
        (owner, repo) tuple if GitHub remote found, None otherwise
    """
    import re

    try:
        remotes = repo.get_remotes()
        repo_obj = repo._repo

        for remote_name in remotes:
            try:
                remote = repo_obj.remote(remote_name)
                for url in remote.urls:
                    # Match GitHub URLs:
                    # https://github.com/owner/repo.git
                    # git@github.com:owner/repo.git
                    match = re.search(r"github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?$", url)
                    if match:
                        owner, repo_name = match.groups()
                        return (owner, repo_name)
            except Exception:
                continue

    except Exception:
        pass

    return None
