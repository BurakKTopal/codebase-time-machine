"""
Git repository wrapper.

Provides a high-level interface for interacting with local git repositories
using GitPython.
"""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from ctm_mcp_server.models.git_models import (
    Author,
    BlameLine,
    BlameResult,
    Branch,
    Commit,
    DiffFile,
    DiffHunk,
    FileChange,
)


def _ensure_str(value: str | bytes) -> str:
    """Convert bytes to str if necessary."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class GitRepoError(Exception):
    """Base exception for git repository errors."""

    pass


class GitRepo:
    """Wrapper for git repository operations."""

    def __init__(self, path: str | Path) -> None:
        """Initialize git repository wrapper.

        Args:
            path: Path to the git repository.

        Raises:
            GitRepoError: If the path is not a valid git repository.
        """
        self.path = Path(path).resolve()
        try:
            self._repo = Repo(self.path)
        except InvalidGitRepositoryError as err:
            raise GitRepoError(f"Not a git repository: {self.path}") from err
        except NoSuchPathError as err:
            raise GitRepoError(f"Path does not exist: {self.path}") from err

    @property
    def name(self) -> str:
        """Get repository name (directory name)."""
        return self.path.name

    @property
    def is_bare(self) -> bool:
        """Check if repository is bare."""
        return self._repo.bare

    @property
    def is_dirty(self) -> bool:
        """Check if working directory has uncommitted changes."""
        return self._repo.is_dirty()

    @property
    def current_branch(self) -> str | None:
        """Get current branch name."""
        try:
            return self._repo.active_branch.name
        except TypeError:
            # Detached HEAD state
            return None

    @property
    def default_branch(self) -> str | None:
        """Get default branch name (usually main or master)."""
        # Try common default branch names
        for name in ["main", "master", "develop"]:
            try:
                self._repo.heads[name]
                return name
            except IndexError:
                continue
        # Return first branch if exists
        if self._repo.heads:
            return self._repo.heads[0].name
        return None

    def get_remotes(self) -> list[str]:
        """Get list of remote names."""
        return [remote.name for remote in self._repo.remotes]

    def get_branches(self, include_remote: bool = False) -> list[Branch]:
        """Get list of branches.

        Args:
            include_remote: Include remote-tracking branches.

        Returns:
            List of Branch objects.
        """
        branches: list[Branch] = []
        current = self.current_branch

        # Local branches
        for head in self._repo.heads:
            commit = head.commit
            message = _ensure_str(commit.message)
            branches.append(
                Branch(
                    name=head.name,
                    is_current=(head.name == current),
                    is_remote=False,
                    last_commit_sha=commit.hexsha,
                    last_commit_date=datetime.fromtimestamp(commit.committed_date, tz=UTC),
                    last_commit_message=message.split("\n")[0],
                )
            )

        # Remote branches
        if include_remote:
            for ref in self._repo.refs:
                if ref.name.startswith("origin/") and ref.name != "origin/HEAD":
                    commit = ref.commit
                    message = _ensure_str(commit.message)
                    branches.append(
                        Branch(
                            name=ref.name,
                            is_current=False,
                            is_remote=True,
                            last_commit_sha=commit.hexsha,
                            last_commit_date=datetime.fromtimestamp(commit.committed_date, tz=UTC),
                            last_commit_message=message.split("\n")[0],
                        )
                    )

        return branches

    def get_commit(self, sha: str) -> Commit:
        """Get a commit by SHA.

        Args:
            sha: Full or abbreviated commit SHA.

        Returns:
            Commit object.

        Raises:
            GitRepoError: If commit not found.
        """
        try:
            git_commit = self._repo.commit(sha)
        except Exception as e:
            raise GitRepoError(f"Commit not found: {sha}") from e

        return self._make_commit(git_commit)

    def _make_commit(self, git_commit: Any) -> Commit:
        """Convert gitpython commit to our Commit model."""
        # Parse PR and issue numbers from commit message
        message = _ensure_str(git_commit.message)
        pr_number = self._extract_pr_number(message)
        issue_numbers = self._extract_issue_numbers(message)

        # Get file changes
        files_changed: list[FileChange] = []
        if git_commit.parents:
            parent = git_commit.parents[0]
            diffs = parent.diff(git_commit)
            for diff in diffs:
                change_type = "M"
                if diff.new_file:
                    change_type = "A"
                elif diff.deleted_file:
                    change_type = "D"
                elif diff.renamed:
                    change_type = "R"

                files_changed.append(
                    FileChange(
                        path=diff.b_path or diff.a_path or "",
                        old_path=diff.a_path if diff.renamed else None,
                        change_type=change_type,
                        additions=0,  # Would need --stat parsing for this
                        deletions=0,
                    )
                )

        return Commit(
            sha=git_commit.hexsha,
            short_sha=git_commit.hexsha[:7],
            message=message,
            subject=message.split("\n")[0],
            author=Author(
                name=git_commit.author.name or "Unknown",
                email=git_commit.author.email or "",
            ),
            committer=Author(
                name=git_commit.committer.name or "Unknown",
                email=git_commit.committer.email or "",
            ),
            authored_date=datetime.fromtimestamp(git_commit.authored_date, tz=UTC),
            committed_date=datetime.fromtimestamp(git_commit.committed_date, tz=UTC),
            parents=[p.hexsha for p in git_commit.parents],
            files_changed=files_changed,
            pr_number=pr_number,
            issue_numbers=issue_numbers,
        )

    def get_file_history(self, file_path: str, max_commits: int = 50) -> list[Commit]:
        """Get commit history for a specific file.

        Args:
            file_path: Path to file (relative to repo root).
            max_commits: Maximum number of commits to return.

        Returns:
            List of commits that modified the file.
        """
        commits: list[Commit] = []
        try:
            for git_commit in self._repo.iter_commits(paths=file_path, max_count=max_commits):
                commits.append(self._make_commit(git_commit))
        except GitCommandError as e:
            raise GitRepoError(f"Error getting file history: {e}") from e

        return commits

    def get_blame(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> BlameResult:
        """Get blame information for a file.

        Args:
            file_path: Path to file (relative to repo root).
            start_line: Starting line number (1-indexed, optional).
            end_line: Ending line number (1-indexed, optional).

        Returns:
            BlameResult with line-by-line blame information.
        """
        try:
            blame_data = self._repo.blame("HEAD", file_path)
        except GitCommandError as e:
            raise GitRepoError(f"Error getting blame: {e}") from e

        lines: list[BlameLine] = []
        line_number = 0

        for blame_entry in blame_data:  # type: ignore[union-attr]
            # blame_entry is a tuple of (commit, list of lines)
            commit: Any = blame_entry[0]
            content_lines: list[Any] = list(blame_entry[1])  # type: ignore[arg-type]
            commit_message = _ensure_str(commit.message)
            for content in content_lines:
                line_number += 1

                # Skip lines outside requested range
                if start_line and line_number < start_line:
                    continue
                if end_line and line_number > end_line:
                    break

                content_str = (
                    _ensure_str(content) if isinstance(content, (str, bytes)) else str(content)
                )
                lines.append(
                    BlameLine(
                        line_number=line_number,
                        content=content_str,
                        commit_sha=commit.hexsha,
                        commit_short_sha=commit.hexsha[:7],
                        author=Author(
                            name=commit.author.name or "Unknown",
                            email=commit.author.email or "",
                        ),
                        committed_date=datetime.fromtimestamp(commit.committed_date, tz=UTC),
                        commit_message=commit_message.split("\n")[0],
                        pr_number=self._extract_pr_number(commit_message),
                        issue_numbers=self._extract_issue_numbers(commit_message),
                    )
                )

            if end_line and line_number > end_line:
                break

        return BlameResult(
            file_path=file_path,
            lines=lines,
            start_line=start_line,
            end_line=end_line,
        )

    def get_diff(self, sha: str) -> list[DiffFile]:
        """Get the diff for a commit.

        Args:
            sha: Commit SHA.

        Returns:
            List of DiffFile objects.
        """
        commit = self._repo.commit(sha)
        if not commit.parents:
            # Initial commit - diff against empty tree
            diffs = commit.diff(None, create_patch=True)
        else:
            diffs = commit.parents[0].diff(commit, create_patch=True)

        result: list[DiffFile] = []
        for diff in diffs:
            change_type = "M"
            if diff.new_file:
                change_type = "A"
            elif diff.deleted_file:
                change_type = "D"
            elif diff.renamed:
                change_type = "R"

            # Parse hunks from diff
            hunks: list[DiffHunk] = []
            if diff.diff:
                hunks = self._parse_diff_hunks(_ensure_str(diff.diff))

            result.append(
                DiffFile(
                    path=diff.b_path or diff.a_path or "",
                    old_path=diff.a_path if diff.renamed else None,
                    change_type=change_type,
                    hunks=hunks,
                    is_binary=diff.diff is None and not diff.deleted_file and not diff.new_file,
                    additions=sum(h.new_count for h in hunks),
                    deletions=sum(h.old_count for h in hunks),
                )
            )

        return result

    def _parse_diff_hunks(self, diff_text: str) -> list[DiffHunk]:
        """Parse diff text into hunks."""
        hunks: list[DiffHunk] = []
        hunk_pattern = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)")

        current_hunk: DiffHunk | None = None
        current_lines: list[str] = []

        for line in diff_text.split("\n"):
            match = hunk_pattern.match(line)
            if match:
                # Save previous hunk
                if current_hunk:
                    current_hunk.lines = current_lines
                    hunks.append(current_hunk)

                # Start new hunk
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1

                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    header=line,
                    lines=[],
                )
                current_lines = []
            elif current_hunk and (
                line.startswith("+") or line.startswith("-") or line.startswith(" ")
            ):
                current_lines.append(line)

        # Save last hunk
        if current_hunk:
            current_hunk.lines = current_lines
            hunks.append(current_hunk)

        return hunks

    def get_contributors(self, max_count: int = 50) -> list[str]:
        """Get list of contributor names.

        Args:
            max_count: Maximum number of contributors to return.

        Returns:
            List of contributor names (most commits first).
        """
        authors: dict[str, int] = {}
        for commit in self._repo.iter_commits(max_count=1000):
            name = commit.author.name or "Unknown"
            authors[name] = authors.get(name, 0) + 1

        # Sort by commit count
        sorted_authors = sorted(authors.items(), key=lambda x: x[1], reverse=True)
        return [name for name, _ in sorted_authors[:max_count]]

    def get_commit_count(self) -> int:
        """Get total number of commits."""
        return sum(1 for _ in self._repo.iter_commits())

    def get_file_at_commit(self, sha: str, file_path: str) -> str:
        """Get file contents at a specific commit.

        Args:
            sha: Commit SHA.
            file_path: Path to file.

        Returns:
            File contents as string.

        Raises:
            GitRepoError: If file not found at commit.
        """
        try:
            commit = self._repo.commit(sha)
            blob = commit.tree / file_path
            content: bytes = blob.data_stream.read()
            return content.decode("utf-8", errors="replace")
        except KeyError as err:
            raise GitRepoError(f"File not found at commit {sha}: {file_path}") from err
        except Exception as e:
            raise GitRepoError(f"Error reading file: {e}") from e

    def pickaxe_search(
        self,
        search_string: str,
        file_path: str | None = None,
        max_commits: int = 20,
        regex: bool = False,
        follow_renames: bool = True,
    ) -> list[Commit]:
        """Find commits that introduced or removed a specific string.

        This uses git's pickaxe feature (git log -S or -G) to find commits
        where the given string was added or removed. This is the best way
        to find when a piece of code was first introduced.

        Args:
            search_string: The string/code to search for.
            file_path: Optional file path to limit the search.
            max_commits: Maximum number of commits to return.
            regex: If True, treat search_string as a regex (uses -G instead of -S).
            follow_renames: If True, follow file renames when file_path is provided.
                This ensures the true introduction commit is found even if the
                file was renamed after the code was added.

        Returns:
            List of commits that added or removed the search string,
            ordered from newest to oldest.

        Raises:
            GitRepoError: If the search fails.
        """
        try:
            # Build arguments for git log
            # GitPython's git.log() handles the executable path properly
            log_kwargs = {
                "format": "%H",
                "n": max_commits,
            }

            if regex:
                log_kwargs["G"] = search_string
            else:
                log_kwargs["S"] = search_string

            # Execute git log with pickaxe
            # Use --follow to trace file renames when searching a specific file
            if file_path:
                if follow_renames:
                    output = self._repo.git.log("--follow", "--", file_path, **log_kwargs)
                else:
                    output = self._repo.git.log("--", file_path, **log_kwargs)
            else:
                output = self._repo.git.log(**log_kwargs)

            if not output.strip():
                return []

            # Parse commit SHAs and get full commit info
            commits: list[Commit] = []
            shas = output.strip().split("\n")
            for sha in shas:
                if sha.strip():
                    commits.append(self.get_commit(sha.strip()))

            return commits

        except GitCommandError as e:
            raise GitRepoError(f"Pickaxe search failed: {e}") from e
        except Exception as e:
            raise GitRepoError(f"Error during pickaxe search: {e}") from e

    @staticmethod
    def _extract_pr_number(message: str) -> int | None:
        """Extract PR number from commit message."""
        # Patterns: (#123), Merge pull request #123, PR #123
        patterns = [
            r"\(#(\d+)\)",  # (#123)
            r"Merge pull request #(\d+)",  # GitHub merge commit
            r"PR #(\d+)",  # PR #123
            r"pull request #(\d+)",  # pull request #123
        ]
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _extract_issue_numbers(message: str) -> list[int]:
        """Extract issue numbers from commit message."""
        # Patterns: #123, fixes #123, closes #123, resolves #123
        pattern = r"(?:fixes?|closes?|resolves?|refs?)?\s*#(\d+)"
        matches = re.findall(pattern, message, re.IGNORECASE)
        return [int(m) for m in matches]
