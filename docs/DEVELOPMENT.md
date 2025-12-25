# Development Guide

Quick reference for common development tasks.

---

## Python Package Development

### Initial Setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# or
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# Clone and install dependencies
git clone https://github.com/burakktopal/codebase-time-machine.git
cd codebase-time-machine
uv sync
```

### Running the Server Locally

```bash
# Run server directly
uv run ctm-server

# Run server via Python module (avoids .exe issues)
uv run python -m ctm_mcp_server.stdio_server

# Run with environment variables
GITHUB_TOKEN=your_token uv run ctm-server  # Linux/macOS
set GITHUB_TOKEN=your_token && uv run ctm-server  # Windows
```

**Cache Database**:
- Default location: `~/.ctm/cache.db`
- Custom location: Set `CTM_CACHE_PATH=/custom/path/cache.db`

### Code Quality

```bash
# Format code
uv run ruff format ctm_mcp_server

# Lint code
uv run ruff check ctm_mcp_server

# Fix linting issues
uv run ruff check --fix ctm_mcp_server

# Type checking
uv run mypy ctm_mcp_server
```

### Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=ctm_mcp_server --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_specific.py

# Run tests in watch mode
uv run pytest-watch
```

---

## PyPI Package Distribution

### Building the Package

```bash
# Clean previous builds
rm -rf dist/
# or on Windows:
# rmdir /s /q dist

# Build wheel and source distribution
python -m build

# Output:
# dist/codebase_time_machine-0.1.1-py3-none-any.whl
# dist/codebase_time_machine-0.1.1.tar.gz
```

### Testing the Build Locally

```bash
# Create fresh test environment
python -m venv test_env
source test_env/bin/activate  # Linux/macOS
# or
test_env\Scripts\activate  # Windows

# Install from local wheel
pip install dist/codebase_time_machine-0.1.1-py3-none-any.whl

# Test it works
ctm-server --version
python -m ctm_mcp_server.stdio_server --help

# Cleanup
deactivate
rm -rf test_env  # Linux/macOS
# or
rmdir /s /q test_env  # Windows
```

### Uploading to TestPyPI

```bash
# Install twine (if not installed)
pip install twine

# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# You'll be prompted for:
# Username: __token__
# Password: your-testpypi-api-token

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --upgrade codebase-time-machine
```

### Uploading to Production PyPI

```bash
# Upload to PyPI
python -m twine upload dist/*

# You'll be prompted for:
# Username: __token__
# Password: your-pypi-api-token
```

### Version Bumping

Before building a new release:

1. **Update version** in `pyproject.toml`:
   ```toml
   version = "0.1.2"  # Increment version
   ```

2. **Update CHANGELOG** (if you have one)

3. **Commit changes**:
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.1.2"
   git tag v0.1.2
   git push && git push --tags
   ```

4. **Build and upload** (see above)

---

## VS Code Extension Development

### Initial Setup

```bash
cd extensions/vscode

# Install dependencies
npm install

# Compile TypeScript
npm run compile
```

### Development Workflow

```bash
# Watch mode (auto-recompile on changes)
npm run watch

# Compile once
npm run compile

# Lint
npm run lint

# Package extension (creates VSIX)
npm run package

# Output: codebase-time-machine-0.1.0.vsix
```

### Testing the Extension

**Method 1: Debug Mode (F5)**
1. Open `extensions/vscode` in VS Code
2. Press `F5` to launch Extension Development Host
3. Test changes in the new window

**Method 2: Install VSIX**
```bash
# Package extension
npm run package

# Install in VS Code
# Extensions → ... → Install from VSIX → select .vsix file
```

### Extension Configuration

**For package installation (default)**:
- No configuration needed
- Extension auto-detects `ctm-server` in PATH

**For local development**:
```json
{
  "ctm.serverPath": "/absolute/path/to/codebase-time-machine"
}
```

Extension auto-detects local repo and uses `uv run python -m ctm_mcp_server.stdio_server`.

**Advanced override**:
```json
{
  "ctm.serverCommand": "uv",
  "ctm.serverArgs": ["run", "python", "-m", "ctm_mcp_server.stdio_server"],
  "ctm.serverPath": "/absolute/path/to/codebase-time-machine"
}
```

---

## Git Workflow

### Creating a Feature Branch

```bash
git checkout -b feature/my-new-feature
# Make changes
git add .
git commit -m "Add my new feature"
git push -u origin feature/my-new-feature
```

### Committing Changes

```bash
# Stage files
git add file1.py file2.py

# Commit with message
git commit -m "Brief description of changes"

# Push to remote
git push
```

### Creating a Pull Request

```bash
# Make sure you're on your feature branch
git checkout feature/my-feature

# Push to remote
git push -u origin feature/my-feature

# Create PR via GitHub CLI (if installed)
gh pr create --title "Feature: My feature" --body "Description of changes"

# Or create manually on GitHub.com
```

---

## Troubleshooting Common Issues

### "ctm-server.exe is locked" (Windows)

**Problem**: `uv run ctm-server` creates .exe that gets locked by VS Code

**Solution**: Use Python module directly
```bash
uv run python -m ctm_mcp_server.stdio_server
```

Or configure VS Code to auto-detect (just set `serverPath`).

### "Module not found" errors

```bash
# Resync dependencies
uv sync

# Force reinstall
rm -rf .venv
uv sync
```

### Extension not loading

1. Restart VS Code
2. Check Output panel: View → Output → Select "Codebase Time Machine"
3. Verify server command in logs

### Package installation fails

```bash
# Clear pip cache
pip cache purge

# Reinstall
pip uninstall codebase-time-machine
pip install codebase-time-machine
```

---

## Useful Commands Reference

### Python Package

| Command | Purpose |
|---------|---------|
| `uv sync` | Install/update dependencies |
| `uv run ctm-server` | Run server |
| `uv run pytest` | Run tests |
| `uv run ruff format .` | Format code |
| `python -m build` | Build package |
| `twine upload dist/*` | Upload to PyPI |

### VS Code Extension

| Command | Purpose |
|---------|---------|
| `npm install` | Install dependencies |
| `npm run compile` | Compile TypeScript |
| `npm run watch` | Auto-compile on changes |
| `npm run package` | Create VSIX installer |

### Git

| Command | Purpose |
|---------|---------|
| `git status` | Check status |
| `git diff` | See changes |
| `git log --oneline` | View commit history |
| `git checkout -b branch-name` | Create new branch |
| `git push origin branch-name` | Push branch to remote |

---

## Project Structure

```
codebase-time-machine/
├── ctm_mcp_server/          # Python MCP server
│   ├── data/                # Data access layer
│   ├── tools/               # MCP tool implementations
│   └── stdio_server.py      # Entry point
├── extensions/
│   └── vscode/              # VS Code extension
│       ├── src/             # TypeScript source
│       └── package.json     # Extension manifest
├── tests/                   # Python tests
├── docs/                    # Documentation
├── pyproject.toml           # Python package config
├── LICENSE                  # AGPL-3.0 license
└── README.md                # Main documentation
```

---

## Getting Help

- **GitHub Issues**: https://github.com/burakktopal/codebase-time-machine/issues
- **MCP Documentation**: https://modelcontextprotocol.io/
- **VS Code Extension API**: https://code.visualstudio.com/api

---

**Last Updated**: 2025-12-25
