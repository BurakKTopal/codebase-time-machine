# Contributing to Codebase Time Machine

Thank you for your interest in contributing to Codebase Time Machine! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Git

### Setting Up Your Development Environment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/codebase-time-machine.git
   cd codebase-time-machine
   ```

2. **Install dependencies with uv:**
   ```bash
   uv sync --all-extras --dev
   ```

   Or with pip:
   ```bash
   pip install -e ".[dev]"
   ```

3. **Set up pre-commit hooks:**
   ```bash
   uv run pre-commit install
   ```

4. **Copy environment template:**
   ```bash
   cp .env.example .env
   # Edit .env with your GitHub token
   ```

## Development Workflow

### Running the MCP Server

```bash
uv run ctm_server.py
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=ctm_mcp_server --cov-report=html

# Run specific test file
uv run pytest tests/unit/test_git_repo.py
```

### Code Quality

```bash
# Format code
uv run black .

# Lint code
uv run ruff check .

# Fix auto-fixable lint issues
uv run ruff check . --fix

# Type checking
uv run mypy ctm_mcp_server
```

### Running Pre-commit Hooks Manually

```bash
uv run pre-commit run --all-files
```

## Code Style

- We use [Black](https://black.readthedocs.io/) for code formatting (line length: 100)
- We use [Ruff](https://docs.astral.sh/ruff/) for linting
- We use [mypy](https://mypy.readthedocs.io/) for type checking
- All functions should have type hints
- All public functions should have docstrings

### Example Function

```python
async def trace_file_history(
    repo_path: str,
    file_path: str,
    max_commits: int = 50,
) -> FileHistoryResult:
    """Trace the history of changes to a specific file.

    Args:
        repo_path: Path to the local git repository.
        file_path: Path to the file (relative to repo root).
        max_commits: Maximum number of commits to return.

    Returns:
        FileHistoryResult containing the list of commits.

    Raises:
        FileNotFoundError: If the file doesn't exist in the repository.
    """
    ...
```

## Project Structure

```
ctm_mcp_server/
├── __init__.py          # Package init with version
├── stdio_server.py      # MCP protocol server
├── models/              # Pydantic data models
├── tools/               # Tool implementations
├── data/                # Git & GitHub data access
├── parsing/             # Tree-sitter code parsing
├── analysis/            # Intent extraction, risk scoring
└── search/              # Vector search
```

## Making Changes

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes and add tests**

3. **Run the test suite:**
   ```bash
   uv run pytest
   ```

4. **Run code quality checks:**
   ```bash
   uv run pre-commit run --all-files
   ```

5. **Commit your changes:**
   ```bash
   git commit -m "feat: add your feature description"
   ```

   We follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` for new features
   - `fix:` for bug fixes
   - `docs:` for documentation changes
   - `refactor:` for code refactoring
   - `test:` for adding tests
   - `chore:` for maintenance tasks

6. **Push and create a pull request:**
   ```bash
   git push origin feature/your-feature-name
   ```

## Adding a New Tool

1. Create the tool implementation in `ctm_mcp_server/tools/`
2. Add the tool schema to `stdio_server.py` in `list_tools()`
3. Add the tool handler to `call_tool()` in `stdio_server.py`
4. Add tests in `tests/unit/` and `tests/integration/`
5. Update documentation if needed

## Questions?

If you have questions, please open an issue on GitHub.
