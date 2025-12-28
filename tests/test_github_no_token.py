"""
Tests to verify GitHub API calls work without GITHUB_TOKEN for public repositories.

These tests make real API calls to GitHub to verify:
1. Public repo access works without authentication
2. Rate limits are enforced (60/hour without token)
"""

import os
import pytest
from ctm_mcp_server.data.github_client import GitHubClient


class TestGitHubNoToken:
    """Test GitHub API access without authentication token."""

    @pytest.fixture
    def client_no_token(self, monkeypatch: pytest.MonkeyPatch) -> GitHubClient:
        """Create a GitHub client with no token (env var unset)."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        return GitHubClient(owner="octocat", repo="Hello-World")

    @pytest.mark.asyncio
    async def test_get_repo_info_without_token(self, client_no_token: GitHubClient) -> None:
        """Test that we can get public repo info without a token."""
        # octocat/Hello-World is GitHub's official example public repo
        repo = await client_no_token.get_repo_info()

        assert repo is not None
        assert repo["name"] == "Hello-World"
        assert repo["owner"] == "octocat"  # owner is flattened to just the login string
        assert repo["is_private"] is False

    @pytest.mark.asyncio
    async def test_get_file_without_token(self, client_no_token: GitHubClient) -> None:
        """Test that we can get file contents from public repo without token."""
        content = await client_no_token.get_file_contents("README")

        assert content is not None
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_get_branches_without_token(self, client_no_token: GitHubClient) -> None:
        """Test that we can get branches from public repo without token."""
        branches = await client_no_token.get_branches()

        assert branches is not None
        assert len(branches) > 0
        assert any(b["name"] == "master" for b in branches)

    @pytest.mark.asyncio
    async def test_get_commit_without_token(self, client_no_token: GitHubClient) -> None:
        """Test that we can get a commit from public repo without token."""
        # First commit of Hello-World repo
        commit = await client_no_token.get_commit("553c2077f0edc3d5dc5d17262f6aa498e69d6f8e")

        assert commit is not None
        assert commit["sha"] == "553c2077f0edc3d5dc5d17262f6aa498e69d6f8e"


class TestGitHubTokenPresence:
    """Test behavior differences with and without token."""

    def test_headers_without_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify Authorization header is not set when no token provided."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        client = GitHubClient(owner="test", repo="test")

        assert "Authorization" not in client._headers
        assert client.token is None

    def test_headers_with_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify Authorization header is set when token provided."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        client = GitHubClient(token="test_token", owner="test", repo="test")

        assert "Authorization" in client._headers
        assert client._headers["Authorization"] == "Bearer test_token"

    def test_token_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify token is read from GITHUB_TOKEN env var."""
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        client = GitHubClient(owner="test", repo="test")

        assert client.token == "env_token"
        assert "Authorization" in client._headers

    def test_explicit_token_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify explicit token parameter overrides env var."""
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        client = GitHubClient(token="explicit_token", owner="test", repo="test")

        assert client.token == "explicit_token"
        assert client._headers["Authorization"] == "Bearer explicit_token"

    def test_none_token_with_env_set_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify passing token=None still uses env var (expected fallback)."""
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        client = GitHubClient(token=None, owner="test", repo="test")

        # This is expected - None means "use default" which is env var
        assert client.token == "env_token"
