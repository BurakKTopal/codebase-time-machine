"""
GitHub API client.

Provides access to GitHub PRs, issues, and comments using the GitHub REST API.
"""

import os
import re
from datetime import datetime
from typing import Any

import httpx
from dotenv import load_dotenv

# Import cache for caching support
from ctm_mcp_server.data.cache import Cache
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

    # Cache TTL constants (in seconds)
    TTL_IMMUTABLE = 0  # Never expire (commits, git trees)
    TTL_LONG = 7 * 24 * 3600  # 7 days (file contents, branches)
    TTL_MEDIUM = 24 * 3600  # 24 hours (repo metadata, commit lists)
    TTL_SHORT = 3600  # 1 hour (PRs, issues, comments)
    TTL_VOLATILE = 30 * 60  # 30 minutes (search results)

    def __init__(
        self,
        token: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        cache: Cache | None = None,
    ) -> None:
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token. If not provided,
                   uses GITHUB_TOKEN environment variable.
            owner: Repository owner (username or organization).
            repo: Repository name.
            cache: Optional Cache instance for API response caching.
                   If None, no caching is performed.
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.owner = owner
        self.repo = repo
        self.cache = cache

        # Build headers
        self._headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self._headers["Authorization"] = f"Bearer {self.token}"

    def _cache_get(self, namespace: str, *args: Any) -> Any | None:
        """Get value from cache if cache is enabled.

        Args:
            namespace: Cache namespace (e.g., "github:get_pull_request").
            *args: Additional cache key components (e.g., pr_number).

        Returns:
            Cached value, or None if not cached or cache disabled.
        """
        if not self.cache:
            return None
        return self.cache.get(namespace, self.owner, self.repo, *args)

    def _cache_set(self, namespace: str, *args: Any, value: Any, ttl: int | None = None) -> None:
        """Set value in cache if cache is enabled.

        Args:
            namespace: Cache namespace (e.g., "github:get_pull_request").
            *args: Additional cache key components (e.g., pr_number).
            value: Value to cache (must be JSON-serializable).
            ttl: Time-to-live in seconds, or None for no expiration.
        """
        if self.cache:
            self.cache.set(namespace, self.owner, self.repo, *args, value=value, ttl=ttl)

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
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Make an API request.

        Args:
            method: HTTP method.
            path: API path.
            extra_headers: Additional headers to merge with default headers.
            **kwargs: Additional arguments for httpx.

        Returns:
            JSON response (dict or list depending on endpoint).

        Raises:
            GitHubClientError: On API errors.
        """
        async with self._get_client() as client:
            # Merge extra headers if provided
            if extra_headers:
                kwargs["headers"] = {**kwargs.get("headers", {}), **extra_headers}

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

    async def _graphql_request(self, query: str, variables: dict[str, Any] | None = None) -> Any:
        """Make a GraphQL API request.

        Args:
            query: GraphQL query string.
            variables: Query variables.

        Returns:
            JSON response data.

        Raises:
            GitHubClientError: On API errors.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.github.com/graphql",
                headers=self._headers,
                json={"query": query, "variables": variables or {}},
                timeout=30.0,
            )

            if response.status_code == 401:
                raise GitHubClientError("GraphQL requires authentication")
            if response.status_code >= 400:
                raise GitHubClientError(f"GraphQL error {response.status_code}: {response.text}")

            data = response.json()
            if "errors" in data:
                raise GitHubClientError(f"GraphQL errors: {data['errors']}")

            return data.get("data", {})

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
        # Check cache first
        cached = self._cache_get("github:get_pull_request", pr_number)
        if cached is not None:
            return PullRequest(**cached)

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

        pr = PullRequest(
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

        # Cache before returning
        self._cache_set(
            "github:get_pull_request", pr_number, value=pr.model_dump(), ttl=self.TTL_SHORT
        )

        return pr

    async def get_pr_comments(self, pr_number: int) -> list[Comment]:
        """Get comments on a PR (issue comments, not review comments)."""
        # Check cache first
        cached = self._cache_get("github:get_pr_comments", pr_number)
        if cached is not None:
            return [Comment(**c) for c in cached]

        data = await self._request("GET", self._repo_path(f"/issues/{pr_number}/comments"))
        comments = [self._parse_comment(c) for c in data]

        # Cache before returning
        self._cache_set(
            "github:get_pr_comments",
            pr_number,
            value=[c.model_dump() for c in comments],
            ttl=self.TTL_SHORT,
        )

        return comments

    async def get_pr_reviews(self, pr_number: int) -> list[Review]:
        """Get reviews on a PR."""
        # Check cache first
        cached = self._cache_get("github:get_pr_reviews", pr_number)
        if cached is not None:
            return [Review(**r) for r in cached]

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

        # Cache before returning
        self._cache_set(
            "github:get_pr_reviews",
            pr_number,
            value=[r.model_dump() for r in reviews],
            ttl=self.TTL_SHORT,
        )

        return reviews

    async def get_pr_review_comments(self, pr_number: int) -> list[Comment]:
        """Get review comments (inline code comments) on a PR."""
        # Check cache first
        cached = self._cache_get("github:get_pr_review_comments", pr_number)
        if cached is not None:
            return [Comment(**c) for c in cached]

        data = await self._request("GET", self._repo_path(f"/pulls/{pr_number}/comments"))
        comments = [self._parse_comment(c) for c in data]

        # Cache before returning
        self._cache_set(
            "github:get_pr_review_comments",
            pr_number,
            value=[c.model_dump() for c in comments],
            ttl=self.TTL_SHORT,
        )

        return comments

    async def get_issue(self, issue_number: int) -> Issue:
        """Get an issue by number.

        Args:
            issue_number: Issue number.

        Returns:
            Issue object.
        """
        # Check cache first
        cached = self._cache_get("github:get_issue", issue_number)
        if cached is not None:
            return Issue(**cached)

        data = await self._request("GET", self._repo_path(f"/issues/{issue_number}"))

        # Get comments
        comments = await self.get_issue_comments(issue_number)

        state = IssueState.OPEN if data.get("state") == "open" else IssueState.CLOSED

        issue = Issue(
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

        # Cache before returning
        self._cache_set(
            "github:get_issue", issue_number, value=issue.model_dump(), ttl=self.TTL_SHORT
        )

        return issue

    async def get_issue_comments(self, issue_number: int) -> list[Comment]:
        """Get comments on an issue."""
        # Check cache first
        cached = self._cache_get("github:get_issue_comments", issue_number)
        if cached is not None:
            return [Comment(**c) for c in cached]

        data = await self._request("GET", self._repo_path(f"/issues/{issue_number}/comments"))
        comments = [self._parse_comment(c) for c in data]

        # Cache before returning
        self._cache_set(
            "github:get_issue_comments",
            issue_number,
            value=[c.model_dump() for c in comments],
            ttl=self.TTL_SHORT,
        )

        return comments

    async def search_prs_for_commit(self, sha: str) -> list[int]:
        """Find PRs that contain a specific commit.

        Uses the GitHub API endpoint /repos/{owner}/{repo}/commits/{sha}/pulls
        which returns only PRs that actually contain the commit (not just mention it).

        Args:
            sha: Commit SHA (full or abbreviated).

        Returns:
            List of PR numbers that contain this commit.
        """
        # Check cache first
        cached = self._cache_get("github:search_prs_for_commit", sha)
        if cached is not None:
            return cached  # type: ignore[no-any-return]  # type: ignore[no-any-return]

        try:
            # Use the proper GitHub API endpoint that returns PRs containing the commit
            # This is more reliable than the search API which returns text matches
            data = await self._request(
                "GET",
                self._repo_path(f"/commits/{sha}/pulls"),
                # Need to specify the preview header for this endpoint
                extra_headers={"Accept": "application/vnd.github.groot-preview+json"},
            )

            # Extract PR numbers from the response
            result = [pr.get("number") for pr in data if pr.get("number")]

        except GitHubNotFoundError:
            # Commit not found in repo - return empty list
            result = []
        except GitHubClientError:
            # Fallback to search API for other errors (e.g., rate limit issues)
            # This is less reliable but better than nothing
            try:
                query = f"repo:{self.owner}/{self.repo} type:pr {sha}"
                data = await self._request(
                    "GET", "/search/issues", params={"q": query, "per_page": 10}
                )
                result = [item.get("number") for item in data.get("items", [])]
            except Exception:
                result = []

        # Cache before returning
        self._cache_set("github:search_prs_for_commit", sha, value=result, ttl=self.TTL_VOLATILE)

        return result

    @staticmethod
    def _extract_linked_issues(body: str) -> list[int]:
        """Extract linked issue numbers from PR body."""
        # Patterns: fixes #123, closes #123, resolves #123
        pattern = r"(?:fixes?|closes?|resolves?)\s+#(\d+)"
        matches = re.findall(pattern, body, re.IGNORECASE)
        return [int(m) for m in matches]

    # GraphQL query for linked issues (REST Timeline API doesn't include issue numbers)
    _GRAPHQL_LINKED_ISSUES = """
        query($owner: String!, $repo: String!, $prNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $prNumber) {
              closingIssuesReferences(first: 10) {
                nodes { number }
              }
            }
          }
        }
    """

    async def get_pr_linked_issues(self, pr_number: int) -> list[int]:
        """Get issues linked to a PR via GitHub's Development sidebar.

        Uses the GraphQL API to find closingIssuesReferences which are issues
        linked to the PR (not just mentioned in text).

        Args:
            pr_number: PR number.

        Returns:
            List of linked issue numbers.
        """
        # Check cache first
        cached = self._cache_get("github:get_pr_linked_issues", pr_number)
        if cached is not None:
            return cached  # type: ignore[no-any-return]  # type: ignore[no-any-return]

        linked_issues: list[int] = []

        try:
            data = await self._graphql_request(
                self._GRAPHQL_LINKED_ISSUES,
                {"owner": self.owner, "repo": self.repo, "prNumber": pr_number},
            )

            pr_data = data.get("repository", {}).get("pullRequest", {})
            nodes = pr_data.get("closingIssuesReferences", {}).get("nodes", [])

            for node in nodes:
                issue_num = node.get("number")
                if issue_num and issue_num != pr_number:
                    linked_issues.append(issue_num)

        except Exception:
            # GraphQL API may fail, fall back gracefully
            pass

        # Deduplicate and cache
        linked_issues = list(set(linked_issues))
        self._cache_set(
            "github:get_pr_linked_issues", pr_number, value=linked_issues, ttl=self.TTL_SHORT
        )

        return linked_issues

    async def get_repo_info(self) -> dict:
        """Get repository information.

        Returns:
            Repository metadata.
        """
        # Check cache first
        cached = self._cache_get("github:get_repo_info")
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        data = await self._request("GET", self._repo_path(""))
        result = {
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

        # Cache before returning
        self._cache_set("github:get_repo_info", value=result, ttl=self.TTL_MEDIUM)

        return result

    async def get_commit(self, sha: str) -> dict:
        """Get commit details.

        Args:
            sha: Commit SHA.

        Returns:
            Commit details.
        """
        # Check cache first (commits are immutable)
        cached = self._cache_get("github:get_commit", sha)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        data = await self._request("GET", self._repo_path(f"/commits/{sha}"))

        commit_data = data.get("commit", {})
        author_data = commit_data.get("author", {})
        committer_data = commit_data.get("committer", {})

        # Extract files changed
        files = []
        for f in data.get("files", []):
            file_info = {
                "path": f.get("filename", ""),
                "status": f.get("status", "modified"),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": f.get("patch"),
            }
            # Capture previous filename for renames (used for following file history)
            if f.get("status") == "renamed" and f.get("previous_filename"):
                file_info["previous_path"] = f.get("previous_filename")
            files.append(file_info)

        result = {
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

        # Cache before returning (commits are immutable - never expire)
        self._cache_set("github:get_commit", sha, value=result, ttl=self.TTL_IMMUTABLE)

        return result

    async def get_commits_batch(self, shas: list[str]) -> dict[str, dict]:
        """Get multiple commits at once (batch operation).

        This is much more efficient than calling get_commit() multiple times
        because it:
        1. Checks cache for all commits first
        2. Fetches only missing commits in parallel
        3. Returns all results in a single response

        Args:
            shas: List of commit SHAs to fetch.

        Returns:
            Dictionary mapping SHA -> commit details.
            Missing/invalid commits will not be in the result.

        Example:
            >>> commits = await client.get_commits_batch(["abc123", "def456", "ghi789"])
            >>> print(commits["abc123"]["message"])
        """
        import asyncio

        if not shas:
            return {}

        # Remove duplicates while preserving order
        unique_shas = list(dict.fromkeys(shas))

        results = {}
        to_fetch = []

        # Check cache for all commits first
        for sha in unique_shas:
            cached = self._cache_get("github:get_commit", sha)
            if cached is not None:
                results[sha] = cached
            else:
                to_fetch.append(sha)

        # Fetch missing commits in parallel
        if to_fetch:

            async def fetch_one(sha: str) -> tuple[str, dict | None]:
                """Fetch a single commit and return (sha, data) tuple."""
                try:
                    # Call get_commit which handles caching
                    data = await self.get_commit(sha)
                    return (sha, data)
                except Exception:
                    # If commit doesn't exist or API error, return None
                    return (sha, None)

            # Fetch all in parallel
            fetch_results = await asyncio.gather(*[fetch_one(sha) for sha in to_fetch])

            # Add successful fetches to results
            for sha, data in fetch_results:
                if data is not None:
                    results[sha] = data

        return results

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
        # Check cache first (include all params in cache key)
        cache_key_params = (path or "", sha or "", per_page, page)
        cached = self._cache_get("github:list_commits", *cache_key_params)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

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

        # Cache before returning
        self._cache_set(
            "github:list_commits", *cache_key_params, value=commits, ttl=self.TTL_MEDIUM
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
        # Check cache first (include path and ref in cache key)
        cached = self._cache_get("github:get_file_contents", path, ref or "")
        if cached is not None:
            return cached  # type: ignore[no-any-return]

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
            result = {
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
        else:
            import base64

            content = ""
            if data.get("encoding") == "base64" and data.get("content"):
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")

            result = {
                "type": "file",
                "path": data.get("path", path),
                "name": data.get("name", ""),
                "size": data.get("size", 0),
                "sha": data.get("sha", ""),
                "content": content,
                "html_url": data.get("html_url"),
            }

        # Cache before returning
        self._cache_set(
            "github:get_file_contents", path, ref or "", value=result, ttl=self.TTL_LONG
        )

        return result

    async def get_branches(self, per_page: int = 30) -> list[dict]:
        """Get repository branches.

        Args:
            per_page: Number of branches per page.

        Returns:
            List of branches.
        """
        # Check cache first
        cached = self._cache_get("github:get_branches", per_page)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        data = await self._request(
            "GET",
            self._repo_path("/branches"),
            params={"per_page": per_page},
        )

        result = [
            {
                "name": b.get("name", ""),
                "sha": b.get("commit", {}).get("sha", ""),
                "protected": b.get("protected", False),
            }
            for b in data
        ]

        # Cache before returning
        self._cache_set("github:get_branches", per_page, value=result, ttl=self.TTL_LONG)

        return result

    async def get_tree(
        self,
        tree_sha: str = "HEAD",
        recursive: bool = True,
    ) -> dict:
        """Get repository file tree.

        Args:
            tree_sha: Tree SHA or branch name (default: HEAD).
            recursive: If True, get entire tree recursively.

        Returns:
            Tree structure with all files and directories.
        """
        # Check cache first (tree_sha might be resolved, so cache by original input)
        cached = self._cache_get("github:get_tree", tree_sha, recursive)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        original_tree_sha = tree_sha

        # If using HEAD or branch name, first get the commit to find tree SHA
        if tree_sha in ("HEAD", "main", "master") or not tree_sha.startswith(
            ("a", "b", "c", "d", "e", "f", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9")
        ):
            # Get default branch info
            repo_data = await self._request("GET", self._repo_path(""))
            default_branch = repo_data.get("default_branch", "main")

            # Get branch commit
            branch_data = await self._request(
                "GET",
                self._repo_path(f"/branches/{default_branch}"),
            )
            tree_sha = (
                branch_data.get("commit", {}).get("commit", {}).get("tree", {}).get("sha", "")
            )

            if not tree_sha:
                # Fallback: get from commit
                commit_sha = branch_data.get("commit", {}).get("sha", "")
                if commit_sha:
                    commit_data = await self._request(
                        "GET",
                        self._repo_path(f"/git/commits/{commit_sha}"),
                    )
                    tree_sha = commit_data.get("tree", {}).get("sha", "")

        params = {}
        if recursive:
            params["recursive"] = "1"

        data = await self._request(
            "GET",
            self._repo_path(f"/git/trees/{tree_sha}"),
            params=params,
        )

        # Process tree entries
        entries = []
        for item in data.get("tree", []):
            entries.append(
                {
                    "path": item.get("path", ""),
                    "type": "dir" if item.get("type") == "tree" else "file",
                    "size": item.get("size", 0) if item.get("type") == "blob" else None,
                    "sha": item.get("sha", ""),
                }
            )

        result = {
            "sha": data.get("sha", ""),
            "truncated": data.get("truncated", False),
            "total_entries": len(entries),
            "entries": entries,
        }

        # Cache before returning (git trees are immutable - never expire)
        self._cache_set(
            "github:get_tree", original_tree_sha, recursive, value=result, ttl=self.TTL_IMMUTABLE
        )

        return result

    async def search_code(
        self,
        query: str,
        per_page: int = 30,
        page: int = 1,
    ) -> dict:
        """Search for code in the repository.

        Args:
            query: Search query (supports GitHub code search syntax).
            per_page: Number of results per page (max 100).
            page: Page number.

        Returns:
            Search results with code matches.
        """
        # Check cache first
        cached = self._cache_get("github:search_code", query, per_page, page)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        # Scope to this repository
        full_query = f"repo:{self.owner}/{self.repo} {query}"

        data = await self._request(
            "GET",
            "/search/code",
            params={
                "q": full_query,
                "per_page": min(per_page, 100),
                "page": page,
            },
        )

        results = []
        for item in data.get("items", []):
            results.append(
                {
                    "name": item.get("name", ""),
                    "path": item.get("path", ""),
                    "sha": item.get("sha", ""),
                    "html_url": item.get("html_url"),
                    "repository": item.get("repository", {}).get("full_name", ""),
                    # Note: GitHub doesn't return file contents in search results
                    # Use get_file_contents to fetch actual content
                }
            )

        result = {
            "total_count": data.get("total_count", 0),
            "incomplete_results": data.get("incomplete_results", False),
            "items": results,
        }

        # Cache before returning
        self._cache_set(
            "github:search_code", query, per_page, page, value=result, ttl=self.TTL_VOLATILE
        )

        return result

    async def search_commits(
        self,
        query: str,
        per_page: int = 30,
        page: int = 1,
    ) -> dict:
        """Search for commits in the repository.

        Args:
            query: Search query (supports GitHub commit search syntax).
            per_page: Number of results per page (max 100).
            page: Page number.

        Returns:
            Search results with commit matches.
        """
        # Check cache first
        cached = self._cache_get("github:search_commits", query, per_page, page)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        # Scope to this repository
        full_query = f"repo:{self.owner}/{self.repo} {query}"

        # Commit search requires a special accept header
        async with self._get_client() as client:
            headers = dict(self._headers)
            headers["Accept"] = "application/vnd.github.cloak-preview+json"

            response = await client.request(
                "GET",
                "/search/commits",
                params={
                    "q": full_query,
                    "per_page": min(per_page, 100),
                    "page": page,
                },
                headers=headers,
            )

            if response.status_code == 404:
                raise GitHubNotFoundError("Commit search not found")
            if response.status_code == 403:
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining == "0":
                    reset_time = response.headers.get("X-RateLimit-Reset")
                    raise GitHubRateLimitError(f"Rate limit exceeded. Resets at {reset_time}")
                raise GitHubClientError(f"Forbidden: {response.text}")
            if response.status_code >= 400:
                raise GitHubClientError(f"API error {response.status_code}: {response.text}")

            data = response.json()

        results = []
        for item in data.get("items", []):
            commit_data = item.get("commit", {})
            author_data = commit_data.get("author", {})
            committer_data = commit_data.get("committer", {})

            results.append(
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
                    "committer": {
                        "name": committer_data.get("name", "Unknown"),
                        "email": committer_data.get("email", ""),
                        "date": committer_data.get("date"),
                    },
                    "html_url": item.get("html_url"),
                }
            )

        result = {
            "total_count": data.get("total_count", 0),
            "incomplete_results": data.get("incomplete_results", False),
            "items": results,
        }

        # Cache before returning
        self._cache_set(
            "github:search_commits", query, per_page, page, value=result, ttl=self.TTL_VOLATILE
        )

        return result

    async def pickaxe_search(
        self,
        search_string: str,
        path: str | None = None,
        max_commits: int = 20,
        regex: bool = False,
        follow_renames: bool = True,
    ) -> dict:
        """Find commits that introduced or removed a specific string.

        This emulates git's pickaxe feature (git log -S) by analyzing commit diffs
        via the GitHub API. Note: This is slower than local pickaxe since it must
        fetch and analyze each commit's diff.

        Args:
            search_string: The string/code to search for.
            path: Optional file path to limit the search.
            max_commits: Maximum number of commits to analyze.
            regex: If True, treat search_string as a regex pattern.
            follow_renames: If True, follow file renames to find the true origin.

        Returns:
            Dictionary with:
                - commits: List of commits where the string was added/removed
                - introduction_commit: The oldest commit (likely when code was added)
                - search_string: The string that was searched
                - rename_chain: List of file paths if renames were followed
        """
        import asyncio

        # Compile regex if needed
        if regex:
            pattern = re.compile(search_string)
        else:
            pattern = None

        all_matching_commits = []
        total_analyzed = 0
        rename_chain = [path] if path else []
        current_path = path
        seen_shas = set()  # Avoid processing the same commit twice

        # Semaphore for limiting concurrent API requests
        semaphore = asyncio.Semaphore(5)

        async def check_commit(
            commit_summary: dict, check_path: str | None
        ) -> tuple[dict | None, str | None]:
            """Check if a commit's diff contains the search string.
            Returns (commit_detail, previous_path) where previous_path is set if a rename was detected.
            """
            sha = commit_summary["sha"]
            try:
                async with semaphore:
                    commit_detail = await self.get_commit(sha)
                files = commit_detail.get("files", [])
                detected_previous_path = None

                for file_info in files:
                    file_path = file_info.get("path", "")

                    # Track renames - check both current path and previous path
                    if check_path:
                        # Check if this file matches our search path
                        is_target_file = file_path == check_path
                        # Also check if this is a rename TO our path (meaning the previous_path is what we want)
                        if file_info.get("status") == "renamed" and file_path == check_path:
                            detected_previous_path = file_info.get("previous_path")

                        if not is_target_file:
                            continue

                    patch = file_info.get("patch", "")
                    if not patch:
                        continue

                    # Check if the search string appears in added/removed lines
                    if regex and pattern:
                        if pattern.search(patch):
                            return (commit_detail, detected_previous_path)
                    else:
                        if search_string in patch:
                            return (commit_detail, detected_previous_path)

                # Even if no match, return previous_path if rename detected (for tracing history)
                if detected_previous_path:
                    return (None, detected_previous_path)
                return (None, None)
            except Exception:
                return (None, None)

        # Follow renames iteratively
        while True:
            # Get file history for current path
            if current_path:
                commits_data = await self.list_commits(path=current_path, per_page=max_commits)
            else:
                commits_data = await self.list_commits(per_page=max_commits)
                # If no path specified, we can't follow renames
                follow_renames = False

            if not commits_data:
                break

            # Filter out already-seen commits
            new_commits = [c for c in commits_data if c["sha"] not in seen_shas]
            for c in new_commits:
                seen_shas.add(c["sha"])

            total_analyzed += len(new_commits)

            # Check commits in parallel
            results = await asyncio.gather(*[check_commit(c, current_path) for c in new_commits])

            # Collect matching commits and detect renames
            previous_path = None
            for result, prev_path in results:
                if result:
                    all_matching_commits.append(
                        {
                            "sha": result["sha"],
                            "short_sha": result["sha"][:7],
                            "message": result["message"],
                            "subject": result["message"].split("\n")[0],
                            "author": result["author"]["name"],
                            "date": result["author"]["date"],
                        }
                    )
                # Track the first rename we find (oldest one in this batch)
                if prev_path and not previous_path:
                    previous_path = prev_path

            # If we found a rename and follow_renames is enabled, continue with old path
            if follow_renames and previous_path and previous_path not in rename_chain:
                rename_chain.append(previous_path)
                current_path = previous_path
                # Continue the loop to search with the old path
            else:
                # No more renames to follow
                break

        # The introduction commit is the oldest one (last in the list)
        introduction_commit = all_matching_commits[-1] if all_matching_commits else None

        result = {
            "commits": all_matching_commits,
            "introduction_commit": introduction_commit,
            "search_string": search_string,
            "total_analyzed": total_analyzed,
        }

        # Include rename chain if renames were followed
        if len(rename_chain) > 1:
            result["rename_chain"] = rename_chain

        return result

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
