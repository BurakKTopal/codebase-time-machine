"""
Git-related data models.

These models represent git objects like commits, branches, diffs, and blame results.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Author(BaseModel):
    """Represents a git commit author or committer."""

    name: str
    email: str

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


class FileChange(BaseModel):
    """Represents a file changed in a commit."""

    path: str
    old_path: str | None = None  # For renames
    change_type: str = Field(
        description="Type of change: A (added), M (modified), D (deleted), R (renamed)"
    )
    additions: int = 0
    deletions: int = 0

    @property
    def is_rename(self) -> bool:
        return self.change_type == "R" and self.old_path is not None


class Commit(BaseModel):
    """Represents a git commit."""

    sha: str = Field(description="Full commit SHA")
    short_sha: str = Field(description="Abbreviated commit SHA (7 chars)")
    message: str = Field(description="Full commit message")
    subject: str = Field(description="First line of commit message")
    author: Author
    committer: Author
    authored_date: datetime
    committed_date: datetime
    parents: list[str] = Field(default_factory=list, description="Parent commit SHAs")
    files_changed: list[FileChange] = Field(default_factory=list)

    # Optional linked data
    pr_number: int | None = Field(default=None, description="Linked PR number if detected")
    issue_numbers: list[int] = Field(default_factory=list, description="Referenced issue numbers")

    @property
    def is_merge_commit(self) -> bool:
        return len(self.parents) > 1


class Branch(BaseModel):
    """Represents a git branch."""

    name: str
    is_current: bool = False
    is_remote: bool = False
    last_commit_sha: str | None = None
    last_commit_date: datetime | None = None
    last_commit_message: str | None = None


class DiffHunk(BaseModel):
    """Represents a hunk within a diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str = Field(description="The @@ header line")
    lines: list[str] = Field(default_factory=list, description="Diff lines with +/-/space prefix")


class DiffFile(BaseModel):
    """Represents the diff for a single file."""

    path: str
    old_path: str | None = None
    change_type: str
    hunks: list[DiffHunk] = Field(default_factory=list)
    is_binary: bool = False

    # Statistics
    additions: int = 0
    deletions: int = 0


class BlameLine(BaseModel):
    """Represents a single line in a blame result."""

    line_number: int
    content: str
    commit_sha: str
    commit_short_sha: str
    author: Author
    committed_date: datetime
    commit_message: str

    # Enhanced context (populated when available)
    pr_number: int | None = None
    issue_numbers: list[int] = Field(default_factory=list)


class BlameResult(BaseModel):
    """Represents the full blame result for a file or range."""

    file_path: str
    lines: list[BlameLine] = Field(default_factory=list)
    start_line: int | None = None
    end_line: int | None = None

    @property
    def unique_commits(self) -> list[str]:
        """Get list of unique commit SHAs in this blame."""
        seen: set[str] = set()
        result: list[str] = []
        for line in self.lines:
            if line.commit_sha not in seen:
                seen.add(line.commit_sha)
                result.append(line.commit_sha)
        return result
