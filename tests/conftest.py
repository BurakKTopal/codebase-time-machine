"""
Pytest configuration and fixtures for CTM tests.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_repo(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a sample git repository for testing.

    This fixture creates a minimal git repository with some commits
    for testing git-related functionality.
    """
    import subprocess

    repo_path = temp_dir / "sample_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial file and commit
    (repo_path / "README.md").write_text("# Sample Repository\n\nInitial content.")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit: add README"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create a Python file and commit
    (repo_path / "main.py").write_text(
        '''"""Main module."""


def hello() -> str:
    """Return a greeting."""
    return "Hello, World!"


if __name__ == "__main__":
    print(hello())
'''
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add main module with hello function"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Make a bugfix commit
    (repo_path / "main.py").write_text(
        '''"""Main module."""


def hello(name: str = "World") -> str:
    """Return a greeting.

    Args:
        name: The name to greet. Defaults to "World".

    Returns:
        A greeting string.
    """
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(hello())
'''
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: add name parameter to hello function"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    yield repo_path
