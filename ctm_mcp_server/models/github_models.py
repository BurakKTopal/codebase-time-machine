"""
GitHub-related data models.

These models represent GitHub entities like PRs, issues, comments, and reviews.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class User(BaseModel):
    """Represents a GitHub user."""

    login: str
    name: str | None = None
    avatar_url: str | None = None


class Label(BaseModel):
    """Represents a GitHub label."""

    name: str
    color: str | None = None
    description: str | None = None


class Comment(BaseModel):
    """Represents a comment on a PR or issue."""

    id: int
    body: str
    author: User
    created_at: datetime
    updated_at: datetime | None = None

    # For PR review comments
    path: str | None = Field(default=None, description="File path for review comments")
    line: int | None = Field(default=None, description="Line number for review comments")
    commit_sha: str | None = Field(default=None, description="Commit SHA for review comments")


class ReviewState(str, Enum):
    """Pull request review states."""

    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    COMMENTED = "COMMENTED"
    DISMISSED = "DISMISSED"
    PENDING = "PENDING"


class Review(BaseModel):
    """Represents a pull request review."""

    id: int
    author: User
    state: ReviewState
    body: str | None = None
    submitted_at: datetime | None = None
    comments: list[Comment] = Field(default_factory=list)


class IssueState(str, Enum):
    """Issue/PR states."""

    OPEN = "open"
    CLOSED = "closed"


class Issue(BaseModel):
    """Represents a GitHub issue."""

    number: int
    title: str
    body: str | None = None
    state: IssueState
    author: User
    labels: list[Label] = Field(default_factory=list)
    assignees: list[User] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None
    closed_at: datetime | None = None
    comments: list[Comment] = Field(default_factory=list)
    comments_count: int = 0

    # URLs
    html_url: str | None = None


class PullRequestState(str, Enum):
    """Pull request specific states."""

    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class PullRequest(BaseModel):
    """Represents a GitHub pull request."""

    number: int
    title: str
    body: str | None = None
    state: PullRequestState
    author: User
    labels: list[Label] = Field(default_factory=list)
    assignees: list[User] = Field(default_factory=list)
    reviewers: list[User] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None
    closed_at: datetime | None = None
    merged_at: datetime | None = None
    merged_by: User | None = None

    # Branch info
    head_ref: str = Field(description="Source branch name")
    base_ref: str = Field(description="Target branch name")
    head_sha: str | None = None
    base_sha: str | None = None

    # Merge info
    merge_commit_sha: str | None = None
    is_merged: bool = False

    # Statistics
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    commits_count: int = 0

    # Comments and reviews
    comments: list[Comment] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    review_comments: list[Comment] = Field(default_factory=list)

    # URLs
    html_url: str | None = None

    # Linked issues
    linked_issues: list[int] = Field(
        default_factory=list, description="Issue numbers linked to this PR"
    )
