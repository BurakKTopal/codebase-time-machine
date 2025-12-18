"""
GitHub API client.

Provides access to GitHub PRs, issues, and comments using the GitHub REST API.
"""

import os
import re
from datetime import datetime

import httpx
from dotenv import load_dotenv

from ctm_mcp_server.models.github_models import (
    Comment,
    Issue,
    IssueState,
    Label,
    PullRequest,
    PullRequestState,
    Review,
    ReviewState,
    User,
)

# Load environment variables
load_dotenv()


class GitHubClientError(Exception):
    """Base exception for GitHub client errors."""

    pass


class GitHubRateLimitError(GitHubClientError):
    """Raised when GitHub rate limit is exceeded."""

    pass


class GitHubNotFoundError(GitHubClientError):
    """Raised when a resource is not found."""

    pass


class GitHubClient:
    """Async client for GitHub REST API."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> None:
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token. If not provided,
                   uses GITHUB_TOKEN environment variable.
            owner: Repository owner (username or organization).
            repo: Repository name.
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.owner = owner
        self.repo = repo

        # Build headers
        self._headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self._headers["Authorization"] = f"Bearer {self.token}"

    def _get_client(self) -> httpx.AsyncClient:
        """Get configured HTTP client."""
        return httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=self._headers,
            timeout=30.0,
            follow_redirects=True,
        )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict | list:
        """Make an API request.

        Args:
            method: HTTP method.
            path: API path.
            **kwargs: Additional arguments for httpx.

        Returns:
            JSON response.

        Raises:
            GitHubClientError: On API errors.
        """
        async with self._get_client() as client:
            response = await client.request(method, path, **kwargs)

            if response.status_code == 404:
                raise GitHubNotFoundError(f"Not found: {path}")
            if response.status_code == 403:
                # Check for rate limit
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining == "0":
                    reset_time = response.headers.get("X-RateLimit-Reset")
                    raise GitHubRateLimitError(f"Rate limit exceeded. Resets at {reset_time}")
                raise GitHubClientError(f"Forbidden: {response.text}")
            if response.status_code >= 400:
                raise GitHubClientError(f"API error {response.status_code}: {response.text}")

            return response.json()

    def _repo_path(self, path: str) -> str:
        """Build repo-specific API path."""
        if not self.owner or not self.repo:
            raise GitHubClientError("Repository owner and name required")
        return f"/repos/{self.owner}/{self.repo}{path}"

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        """Parse ISO datetime string."""
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _parse_user(data: dict) -> User:
        """Parse user from API response."""
        return User(
            login=data.get("login", "unknown"),
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
        )

    @staticmethod
    def _parse_label(data: dict) -> Label:
        """Parse label from API response."""
        return Label(
            name=data.get("name", ""),
            color=data.get("color"),
            description=data.get("description"),
        )

    def _parse_comment(self, data: dict) -> Comment:
        """Parse comment from API response."""
        return Comment(
            id=data.get("id", 0),
            body=data.get("body", ""),
            author=self._parse_user(data.get("user", {})),
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            updated_at=self._parse_datetime(data.get("updated_at")),
            path=data.get("path"),
            line=data.get("line") or data.get("original_line"),
            commit_sha=data.get("commit_id"),
        )

    async def get_pull_request(self, pr_number: int) -> PullRequest:
        """Get a pull request by number.

        Args:
            pr_number: PR number.

        Returns:
            PullRequest object.
        """
        data = await self._request("GET", self._repo_path(f"/pulls/{pr_number}"))

        # Determine state
        if data.get("merged"):
            state = PullRequestState.MERGED
        elif data.get("state") == "closed":
            state = PullRequestState.CLOSED
        else:
            state = PullRequestState.OPEN

        # Get comments
        comments = await self.get_pr_comments(pr_number)

        # Get reviews
        reviews = await self.get_pr_reviews(pr_number)

        # Get review comments
        review_comments = await self.get_pr_review_comments(pr_number)

        # Extract linked issues from body
        linked_issues = self._extract_linked_issues(data.get("body") or "")

        return PullRequest(
            number=data.get("number", pr_number),
            title=data.get("title", ""),
            body=data.get("body"),
            state=state,
            author=self._parse_user(data.get("user", {})),
            labels=[self._parse_label(lbl) for lbl in data.get("labels", [])],
            assignees=[self._parse_user(usr) for usr in data.get("assignees", [])],
            reviewers=[self._parse_user(usr) for usr in data.get("requested_reviewers", [])],
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            updated_at=self._parse_datetime(data.get("updated_at")),
            closed_at=self._parse_datetime(data.get("closed_at")),
            merged_at=self._parse_datetime(data.get("merged_at")),
            merged_by=(self._parse_user(data["merged_by"]) if data.get("merged_by") else None),
            head_ref=data.get("head", {}).get("ref", ""),
            base_ref=data.get("base", {}).get("ref", ""),
            head_sha=data.get("head", {}).get("sha"),
            base_sha=data.get("base", {}).get("sha"),
            merge_commit_sha=data.get("merge_commit_sha"),
            is_merged=data.get("merged", False),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
            commits_count=data.get("commits", 0),
            comments=comments,
            reviews=reviews,
            review_comments=review_comments,
            html_url=data.get("html_url"),
            linked_issues=linked_issues,
        )

    async def get_pr_comments(self, pr_number: int) -> list[Comment]:
        """Get comments on a PR (issue comments, not review comments)."""
        data = await self._request("GET", self._repo_path(f"/issues/{pr_number}/comments"))
        return [self._parse_comment(c) for c in data]

    async def get_pr_reviews(self, pr_number: int) -> list[Review]:
        """Get reviews on a PR."""
        data = await self._request("GET", self._repo_path(f"/pulls/{pr_number}/reviews"))
        reviews = []
        for r in data:
            try:
                state = ReviewState(r.get("state", "COMMENTED"))
            except ValueError:
                state = ReviewState.COMMENTED

            reviews.append(
                Review(
                    id=r.get("id", 0),
                    author=self._parse_user(r.get("user", {})),
                    state=state,
                    body=r.get("body"),
                    submitted_at=self._parse_datetime(r.get("submitted_at")),
                )
            )
        return reviews

    async def get_pr_review_comments(self, pr_number: int) -> list[Comment]:
        """Get review comments (inline code comments) on a PR."""
        data = await self._request("GET", self._repo_path(f"/pulls/{pr_number}/comments"))
        return [self._parse_comment(c) for c in data]

    async def get_issue(self, issue_number: int) -> Issue:
        """Get an issue by number.

        Args:
            issue_number: Issue number.

        Returns:
            Issue object.
        """
        data = await self._request("GET", self._repo_path(f"/issues/{issue_number}"))

        # Get comments
        comments = await self.get_issue_comments(issue_number)

        state = IssueState.OPEN if data.get("state") == "open" else IssueState.CLOSED

        return Issue(
            number=data.get("number", issue_number),
            title=data.get("title", ""),
            body=data.get("body"),
            state=state,
            author=self._parse_user(data.get("user", {})),
            labels=[self._parse_label(lbl) for lbl in data.get("labels", [])],
            assignees=[self._parse_user(usr) for usr in data.get("assignees", [])],
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            updated_at=self._parse_datetime(data.get("updated_at")),
            closed_at=self._parse_datetime(data.get("closed_at")),
            comments=comments,
            comments_count=data.get("comments", 0),
            html_url=data.get("html_url"),
        )

    async def get_issue_comments(self, issue_number: int) -> list[Comment]:
        """Get comments on an issue."""
        data = await self._request("GET", self._repo_path(f"/issues/{issue_number}/comments"))
        return [self._parse_comment(c) for c in data]

    async def search_prs_for_commit(self, sha: str) -> list[int]:
        """Search for PRs that include a commit.

        Args:
            sha: Commit SHA.

        Returns:
            List of PR numbers.
        """
        # GitHub search API
        query = f"repo:{self.owner}/{self.repo} type:pr {sha}"
        data = await self._request("GET", "/search/issues", params={"q": query, "per_page": 10})

        return [item.get("number") for item in data.get("items", [])]

    @staticmethod
    def _extract_linked_issues(body: str) -> list[int]:
        """Extract linked issue numbers from PR body."""
        # Patterns: fixes #123, closes #123, resolves #123
        pattern = r"(?:fixes?|closes?|resolves?)\s+#(\d+)"
        matches = re.findall(pattern, body, re.IGNORECASE)
        return [int(m) for m in matches]

    async def get_repo_info(self) -> dict:
        """Get repository information.

        Returns:
            Repository metadata.
        """
        data = await self._request("GET", self._repo_path(""))
        return {
            "name": data.get("name", ""),
            "full_name": data.get("full_name", ""),
            "description": data.get("description"),
            "owner": data.get("owner", {}).get("login", ""),
            "default_branch": data.get("default_branch", "main"),
            "is_private": data.get("private", False),
            "is_fork": data.get("fork", False),
            "language": data.get("language"),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "html_url": data.get("html_url"),
        }

    async def get_commit(self, sha: str) -> dict:
        """Get commit details.

        Args:
            sha: Commit SHA.

        Returns:
            Commit details.
        """
        data = await self._request("GET", self._repo_path(f"/commits/{sha}"))

        commit_data = data.get("commit", {})
        author_data = commit_data.get("author", {})
        committer_data = commit_data.get("committer", {})

        # Extract files changed
        files = []
        for f in data.get("files", []):
            files.append(
                {
                    "path": f.get("filename", ""),
                    "status": f.get("status", "modified"),
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0),
                    "patch": f.get("patch"),
                }
            )

        return {
            "sha": data.get("sha", sha),
            "message": commit_data.get("message", ""),
            "author": {
                "name": author_data.get("name", "Unknown"),
                "email": author_data.get("email", ""),
                "date": author_data.get("date"),
            },
            "committer": {
                "name": committer_data.get("name", "Unknown"),
                "email": committer_data.get("email", ""),
                "date": committer_data.get("date"),
            },
            "parents": [p.get("sha") for p in data.get("parents", [])],
            "files": files,
            "stats": {
                "additions": data.get("stats", {}).get("additions", 0),
                "deletions": data.get("stats", {}).get("deletions", 0),
                "total": data.get("stats", {}).get("total", 0),
            },
            "html_url": data.get("html_url"),
        }

    async def list_commits(
        self,
        path: str | None = None,
        sha: str | None = None,
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict]:
        """List commits in repository.

        Args:
            path: Filter commits to a specific file path.
            sha: SHA or branch to start listing from.
            per_page: Number of commits per page.
            page: Page number.

        Returns:
            List of commit summaries.
        """
        params: dict[str, str | int] = {"per_page": per_page, "page": page}
        if path:
            params["path"] = path
        if sha:
            params["sha"] = sha

        data = await self._request("GET", self._repo_path("/commits"), params=params)

        commits = []
        for item in data:
            commit_data = item.get("commit", {})
            author_data = commit_data.get("author", {})

            commits.append(
                {
                    "sha": item.get("sha", ""),
                    "short_sha": item.get("sha", "")[:7],
                    "message": commit_data.get("message", ""),
                    "subject": commit_data.get("message", "").split("\n")[0],
                    "author": {
                        "name": author_data.get("name", "Unknown"),
                        "email": author_data.get("email", ""),
                        "date": author_data.get("date"),
                    },
                    "html_url": item.get("html_url"),
                }
            )

        return commits

    async def get_file_contents(
        self,
        path: str,
        ref: str | None = None,
    ) -> dict:
        """Get file contents at a specific ref.

        Args:
            path: File path relative to repo root.
            ref: Git ref (branch, tag, SHA). Defaults to default branch.

        Returns:
            File contents and metadata.
        """
        params = {}
        if ref:
            params["ref"] = ref

        data = await self._request(
            "GET",
            self._repo_path(f"/contents/{path}"),
            params=params,
        )

        # Handle file vs directory
        if isinstance(data, list):
            # It's a directory
            return {
                "type": "directory",
                "path": path,
                "entries": [
                    {
                        "name": item.get("name", ""),
                        "path": item.get("path", ""),
                        "type": item.get("type", ""),
                        "size": item.get("size", 0),
                    }
                    for item in data
                ],
            }

        import base64

        content = ""
        if data.get("encoding") == "base64" and data.get("content"):
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")

        return {
            "type": "file",
            "path": data.get("path", path),
            "name": data.get("name", ""),
            "size": data.get("size", 0),
            "sha": data.get("sha", ""),
            "content": content,
            "html_url": data.get("html_url"),
        }

    async def get_branches(self, per_page: int = 30) -> list[dict]:
        """Get repository branches.

        Args:
            per_page: Number of branches per page.

        Returns:
            List of branches.
        """
        data = await self._request(
            "GET",
            self._repo_path("/branches"),
            params={"per_page": per_page},
        )

        return [
            {
                "name": b.get("name", ""),
                "sha": b.get("commit", {}).get("sha", ""),
                "protected": b.get("protected", False),
            }
            for b in data
        ]

    @classmethod
    def from_remote_url(cls, remote_url: str, token: str | None = None) -> "GitHubClient":
        """Create client from git remote URL.

        Args:
            remote_url: Git remote URL (https or ssh).
            token: Optional GitHub token.

        Returns:
            Configured GitHubClient.
        """
        # Parse owner/repo from URL
        # https://github.com/owner/repo.git
        # git@github.com:owner/repo.git
        patterns = [
            r"github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?$",
        ]

        for pattern in patterns:
            match = re.search(pattern, remote_url)
            if match:
                owner, repo = match.groups()
                return cls(token=token, owner=owner, repo=repo)

        raise GitHubClientError(f"Could not parse GitHub URL: {remote_url}")
