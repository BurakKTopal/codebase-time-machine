"""
Tool result models with factory methods.

These models wrap tool outputs with success/error handling,
following the pattern from the mcp-registry reference.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from ctm_mcp_server.models.git_models import BlameLine, Branch, Commit


class BaseResult(BaseModel):
    """Base class for all tool results."""

    success: bool
    error: str | None = None

    @classmethod
    def create_error(cls, error: str) -> "BaseResult":
        """Create an error result."""
        return cls(success=False, error=error)


class RepoInfoResult(BaseResult):
    """Result for get_repo_info tool."""

    name: str | None = None
    path: str | None = None
    default_branch: str | None = None
    current_branch: str | None = None
    is_bare: bool = False
    is_dirty: bool = False
    branches_count: int = 0
    commits_count: int = 0
    contributors: list[str] = Field(default_factory=list)
    remotes: list[str] = Field(default_factory=list)
    last_commit_sha: str | None = None
    last_commit_date: datetime | None = None
    last_commit_message: str | None = None

    @classmethod
    def create_success(
        cls,
        name: str,
        path: str,
        default_branch: str | None = None,
        current_branch: str | None = None,
        is_bare: bool = False,
        is_dirty: bool = False,
        branches_count: int = 0,
        commits_count: int = 0,
        contributors: list[str] | None = None,
        remotes: list[str] | None = None,
        last_commit_sha: str | None = None,
        last_commit_date: datetime | None = None,
        last_commit_message: str | None = None,
    ) -> "RepoInfoResult":
        """Create a success result with repo info."""
        return cls(
            success=True,
            name=name,
            path=path,
            default_branch=default_branch,
            current_branch=current_branch,
            is_bare=is_bare,
            is_dirty=is_dirty,
            branches_count=branches_count,
            commits_count=commits_count,
            contributors=contributors or [],
            remotes=remotes or [],
            last_commit_sha=last_commit_sha,
            last_commit_date=last_commit_date,
            last_commit_message=last_commit_message,
        )


class BranchListResult(BaseResult):
    """Result for list_branches tool."""

    branches: list[Branch] = Field(default_factory=list)
    current_branch: str | None = None

    @classmethod
    def create_success(
        cls,
        branches: list[Branch],
        current_branch: str | None = None,
    ) -> "BranchListResult":
        """Create a success result with branches."""
        return cls(
            success=True,
            branches=branches,
            current_branch=current_branch,
        )


class CommitResult(BaseResult):
    """Result for get_commit tool."""

    commit: Commit | None = None

    @classmethod
    def create_success(cls, commit: Commit) -> "CommitResult":
        """Create a success result with commit."""
        return cls(success=True, commit=commit)


class FileHistoryResult(BaseResult):
    """Result for trace_file_history tool."""

    file_path: str | None = None
    commits: list[Commit] = Field(default_factory=list)
    total_commits: int = 0

    @classmethod
    def create_success(
        cls,
        file_path: str,
        commits: list[Commit],
        total_commits: int | None = None,
    ) -> "FileHistoryResult":
        """Create a success result with file history."""
        return cls(
            success=True,
            file_path=file_path,
            commits=commits,
            total_commits=total_commits or len(commits),
        )


class IntentType(str, Enum):
    """Types of commit intent."""

    BUGFIX = "bugfix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DOCS = "docs"
    TEST = "test"
    CHORE = "chore"
    WORKAROUND = "workaround"
    REVERT = "revert"
    MERGE = "merge"
    UNKNOWN = "unknown"


class ExplainCommitResult(BaseResult):
    """Result for explain_commit tool."""

    sha: str | None = None
    intent: IntentType = IntentType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str | None = None
    details: str | None = None

    # Evidence
    keywords_found: list[str] = Field(default_factory=list)
    conventional_commit_type: str | None = None
    pr_number: int | None = None
    issue_numbers: list[int] = Field(default_factory=list)

    @classmethod
    def create_success(
        cls,
        sha: str,
        intent: IntentType,
        confidence: float,
        summary: str,
        details: str | None = None,
        keywords_found: list[str] | None = None,
        conventional_commit_type: str | None = None,
        pr_number: int | None = None,
        issue_numbers: list[int] | None = None,
    ) -> "ExplainCommitResult":
        """Create a success result with commit explanation."""
        return cls(
            success=True,
            sha=sha,
            intent=intent,
            confidence=confidence,
            summary=summary,
            details=details,
            keywords_found=keywords_found or [],
            conventional_commit_type=conventional_commit_type,
            pr_number=pr_number,
            issue_numbers=issue_numbers or [],
        )


class BlameWithContextResult(BaseResult):
    """Result for blame_with_context tool."""

    file_path: str | None = None
    lines: list[BlameLine] = Field(default_factory=list)
    start_line: int | None = None
    end_line: int | None = None
    unique_commits_count: int = 0

    @classmethod
    def create_success(
        cls,
        file_path: str,
        lines: list[BlameLine],
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> "BlameWithContextResult":
        """Create a success result with blame data."""
        unique_commits = len({line.commit_sha for line in lines})
        return cls(
            success=True,
            file_path=file_path,
            lines=lines,
            start_line=start_line,
            end_line=end_line,
            unique_commits_count=unique_commits,
        )
