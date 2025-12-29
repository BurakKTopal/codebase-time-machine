# Contributing to Codebase Time Machine

Thank you for your interest in contributing to Codebase Time Machine! This document provides guidelines, architecture details, and instructions for contributing.

## Table of Contents

- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Local Development](#local-development)
- [Project Architecture](#project-architecture)
- [MCP Server Deep Dive](#mcp-server-deep-dive)
- [VS Code Extension Deep Dive](#vs-code-extension-deep-dive)
- [Adding a New Tool](#adding-a-new-tool)
- [Testing Strategy](#testing-strategy)
- [Building & Distribution](#building--distribution)
- [CI/CD Pipeline](#cicd-pipeline)
- [Release Process](#release-process)
- [Troubleshooting](#troubleshooting)
- [Code Style](#code-style)
- [Commands Reference](#commands-reference)

---

## Quick Start

```bash
# Clone repository
git clone https://github.com/BurakKTopal/codebase-time-machine.git
cd codebase-time-machine

# MCP Server (Python)
uv sync --all-extras --dev
uv run pytest                    # Run tests
uv run ctm-server               # Run server

# VS Code Extension
cd extensions/vscode
npm install
npm run compile
npm run package                  # Create VSIX
```

---

## Development Setup

### Prerequisites

- **Python 3.11+**
- **Node.js 18+** (for VS Code extension)
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **Git**
- **Visual Studio Code 1.80.0+** (for extension development)

Verify installation:
```bash
python --version   # 3.11+
node --version     # 18+
uv --version       # Latest
code --version     # 1.80+
```

### Installing uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### MCP Server Setup

```bash
# Clone the repository
git clone https://github.com/BurakKTopal/codebase-time-machine.git
cd codebase-time-machine

# Install Python dependencies
uv sync --all-extras --dev
```

### VS Code Extension Setup

```bash
cd extensions/vscode

# Install dependencies
npm install

# Compile TypeScript
npm run compile

# Run tests
npm test

# Package extension
npm run package
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | No | GitHub token for higher rate limits (5000/hr vs 60/hr) and private repo access |
| `CTM_CACHE_PATH` | No | Custom path for SQLite cache (default: `~/.ctm/cache.db`) |

---

## Local Development

### Running the MCP Server

```bash
# Run server directly
uv run ctm-server

# Run server via Python module (avoids .exe issues on Windows)
uv run python -m ctm_mcp_server.stdio_server

# Run with environment variables
GITHUB_TOKEN=your_token uv run ctm-server              # Linux/macOS
set GITHUB_TOKEN=your_token && uv run ctm-server       # Windows
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

# Fix linting issues automatically
uv run ruff check --fix ctm_mcp_server

# Type checking
uv run mypy ctm_mcp_server --ignore-missing-imports
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=ctm_mcp_server --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_parser.py -v

# Run tests matching pattern
uv run pytest -k "test_github" -v
```

### VS Code Extension Development

#### Watch Mode (Auto-Recompile)

```bash
cd extensions/vscode
npm run watch
```

#### Debug Mode (F5)

1. Open `extensions/vscode` folder in VS Code
2. Press `F5` or Run → Start Debugging
3. A new "Extension Development Host" window opens
4. Test the extension in this window
5. Console output appears in the original window's Debug Console

#### Reload After Changes

```bash
# Recompile
npm run compile

# In Extension Development Host: press Ctrl+R (Cmd+R) to reload
```

### Extension Configuration for Local Development

**Default (PyPI package)**:
- No configuration needed
- Extension runs `python -m ctm_mcp_server.stdio_server` by default

**For local development**:
```json
{
  "ctm.serverPath": "/absolute/path/to/codebase-time-machine"
}
```

Extension auto-detects local repo and uses `uv run python -m ctm_mcp_server.stdio_server`.

**Advanced override** (in settings.json):
```json
{
  "ctm.serverCommand": ["uv", "run", "python", "-m", "ctm_mcp_server.stdio_server"],
  "ctm.serverPath": "/absolute/path/to/codebase-time-machine"
}
```

---

## Project Architecture

```
codebase-time-machine/
├── ctm_mcp_server/           # Python MCP server (32 tools)
│   ├── stdio_server.py       # MCP protocol entry point
│   ├── data/                 # Data access layer
│   │   ├── github_client.py  # GitHub API client with caching
│   │   ├── git_repo.py       # Local git operations
│   │   └── cache.py          # SQLite caching layer
│   ├── models/               # Pydantic data models
│   ├── parsing/              # Tree-sitter code parsing
│   └── utils/                # Helpers and decorators
├── extensions/vscode/        # VS Code extension (TypeScript)
│   └── src/
│       ├── extension.ts      # Extension entry point
│       ├── agent.ts          # Investigation agent loop
│       ├── mcpClient.ts      # MCP server communication
│       ├── factStore.ts      # Token optimization layer
│       ├── providers/        # LLM providers (Anthropic, OpenAI, Gemini)
│       └── ui/               # VS Code webview panels
├── tests/                    # Python tests
├── CLAUDE.md                 # Agent guide (for Claude Code users)
└── ctm_server.py             # Convenience entry point
```

### Design Principles

1. **Aggregate, don't wrap**: Tools combine multiple data sources in one call (blame + PR + issues)
2. **Cache intelligently**: Commits are immutable (cache forever), PRs change (cache 1 hour)
3. **Optimize for LLMs**: Reduce token usage through batching and fact extraction

---

## MCP Server Deep Dive

### Core Components

#### 1. `stdio_server.py` - MCP Protocol Handler

The main entry point that implements the [Model Context Protocol](https://modelcontextprotocol.io/). It:
- Lists available tools via `list_tools()`
- Handles tool calls via `call_tool()`
- Communicates over stdio with JSON-RPC

```python
# Example tool registration pattern
@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_line_context",
            description="...",
            inputSchema={...}
        ),
        # ... other tools
    ]
```

#### 2. `data/github_client.py` - GitHub API Client

Handles all GitHub API interactions with intelligent caching:

```python
class GitHubClient:
    async def get_line_context(
        self,
        file_path: str,
        line_start: int,
        line_end: int,
        history_depth: int = 1,
        include_discussions: bool = True
    ) -> LineContextResult:
        # 1. Git blame to find last modifier
        # 2. Pickaxe search to find original introduction
        # 3. Fetch associated PR (if exists)
        # 4. Extract linked issues
        # 5. Return aggregated result
```

#### 3. `data/cache.py` - SQLite Caching Layer

TTL-based caching with different strategies per data type:

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Commits | Never expire | Immutable (SHA = content hash) |
| File at commit | Never expire | Immutable |
| Git trees | Never expire | Immutable |
| Repository metadata | 24 hours | Rarely changes |
| PRs and issues | 1 hour | May get new comments |
| Search results | 30 minutes | Index updates |

```python
# Cache key pattern
cache_key = f"github:{owner}/{repo}:commit:{sha}"
```

#### 4. `parsing/parser.py` - Tree-sitter Code Parsing

Extracts symbols (functions, classes, methods) from source code:

```python
# Supported languages
SUPPORTED_LANGUAGES = ["python", "javascript", "typescript", "go", "rust", "c", "cpp"]

# Example output
{
    "symbols": [
        {"name": "MyClass", "type": "class", "line_start": 10, "line_end": 50},
        {"name": "my_function", "type": "function", "line_start": 52, "line_end": 60}
    ]
}
```

### Tool Categories

#### Flagship Tools (Use These First)
- `get_line_context` / `get_local_line_context` - The primary investigation tool

#### Fast Tools
- `get_github_file`, `list_github_tree`, `get_github_file_symbols`

#### Analysis Tools
- `explain_file`, `get_github_file_history`, `get_code_owners`

#### Deep Analysis
- `trace_github_symbol_history`, `get_change_coupling`

#### Search (Last Resort)
- `search_github_code`, `search_github_commits`

---

## VS Code Extension Deep Dive

### Architecture Overview

The extension uses a **token-efficient agentic loop** that minimizes API costs:

```
┌─────────────────────────────────────────────────────────┐
│                    VS Code Extension                     │
├─────────────────────────────────────────────────────────┤
│  User selects code → Right-click → "Why does this       │
│  code exist?" → Extension starts investigation          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │ Tool Pruning │ →  │  FactStore   │ →  │   Agent   │  │
│  │  (32 → 10)   │    │ (extract +   │    │   Loop    │  │
│  │              │    │  discard)    │    │           │  │
│  └──────────────┘    └──────────────┘    └───────────┘  │
│         │                   │                  │         │
│         └───────────────────┴──────────────────┘         │
│                          ↓                               │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              MCP Server (32 tools)                   │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Token Optimization Strategies

#### 1. Tool Pruning (32 → 10 tools)

Instead of sending all 32 tool schemas to the LLM, we curate 10 essential tools:

```typescript
// src/constants.ts
export const CORE_TOOLS = [
    'get_local_line_context',   // Primary tool
    'get_pr',
    'get_issue',
    'search_prs_for_commit',
    'get_github_file_history',
    'get_github_commits_batch',
    'explain_file',
    'get_commit_diff',
    'pickaxe_search',
    'get_code_owners',
];
```

**Impact**: ~70% reduction in tool schema tokens.

#### 2. FactStore (Extract Facts, Discard Raw Data)

Tool results can be huge (a PR with 50 comments = thousands of tokens). FactStore extracts only what matters:

```typescript
// src/factStore.ts
class FactStore {
    addToolResult(toolName: string, result: any): void {
        // Extract key facts
        const facts = this.extractFacts(toolName, result);

        // Store compact facts, discard raw result
        this.facts.push(...facts);
    }

    extractFacts(toolName: string, result: any): Fact[] {
        // PR result (2000 tokens) → compact facts (50 tokens)
        // - PR #123: "Fix race condition" by Alice
        // - Linked to issue #456
        // - Key comment: "This fixes the crash in..."
    }
}
```

**Impact**: ~90% reduction in context accumulation.

#### 3. State-Based Prompts (Not Message Accumulation)

Traditional approach:
```
[System] + [User] + [Assistant] + [Tool1] + [Assistant] + [Tool2] + ...
                                  ↑ grows unbounded
```

CTM approach:
```
[System] + [Current State] + [Facts So Far] + [Next Action]
           ↑ constant size
```

**Impact**: Context usage stays flat regardless of investigation length.

#### 4. Investigation Phases

| Phase | Tool Calls | Behavior |
|-------|------------|----------|
| **Investigate** | 1 to ~75% of budget | Gather facts, follow leads |
| **Synthesize** | ~75% to 100% | Stop tools, write final answer |

### Core Files

| File | Purpose |
|------|---------|
| `extension.ts` | VS Code activation, command registration |
| `agent.ts` | Investigation loop, LLM orchestration |
| `mcpClient.ts` | Spawns and communicates with MCP server |
| `factStore.ts` | Token optimization, fact extraction |
| `providers/*.ts` | Anthropic, OpenAI, Gemini adapters |
| `ui/contextPanel.ts` | Webview panel for results |
| `SYSTEM_PROMPT.md` | Agent instructions (embedded in extension) |

### Adding New Commands

1. **Register command** in `package.json`:
   ```json
   {
     "contributes": {
       "commands": [
         {
           "command": "ctm.myNewCommand",
           "title": "CTM: My New Feature"
         }
       ]
     }
   }
   ```

2. **Implement handler** in `src/extension.ts`:
   ```typescript
   const disposable = vscode.commands.registerCommand(
     'ctm.myNewCommand',
     async () => {
       // Implementation here
     }
   );
   context.subscriptions.push(disposable);
   ```

3. **Compile and test**:
   ```bash
   npm run compile
   # Press F5 to test
   ```

### Adding New Settings

1. **Define setting** in `package.json`:
   ```json
   {
     "contributes": {
       "configuration": {
         "properties": {
           "ctm.myNewSetting": {
             "type": "string",
             "default": "defaultValue",
             "description": "Description of the setting"
           }
         }
       }
     }
   }
   ```

2. **Read setting** in code:
   ```typescript
   const config = vscode.workspace.getConfiguration('ctm');
   const value = config.get<string>('myNewSetting');
   ```

### Cost Comparison

| Approach | Tokens | Cost per Investigation |
|----------|--------|------------------------|
| Naive (all tools + full accumulation) | 400k-500k | $0.50-$2.00+ |
| Window pruning (last N messages) | 100k-150k | $0.15-$0.30 |
| **CTM Design** (FactStore + pruning) | **20k-40k** | **< $0.05** |

---

## Adding a New Tool

### Step 1: Define the Tool Schema

In `ctm_mcp_server/stdio_server.py`, add to `list_tools()`:

```python
types.Tool(
    name="my_new_tool",
    description="Brief description of what it does",
    inputSchema={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner"},
            "repo": {"type": "string", "description": "Repository name"},
            "my_param": {"type": "string", "description": "What this param does"},
        },
        "required": ["owner", "repo", "my_param"],
    },
)
```

### Step 2: Implement the Handler

In `call_tool()` in `stdio_server.py`:

```python
elif name == "my_new_tool":
    owner = arguments["owner"]
    repo = arguments["repo"]
    my_param = arguments["my_param"]

    client = GitHubClient(owner=owner, repo=repo)
    result = await client.my_new_method(my_param)

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
```

### Step 3: Implement the Logic

In `ctm_mcp_server/data/github_client.py`:

```python
async def my_new_method(self, my_param: str) -> dict:
    """Description of what this method does.

    Args:
        my_param: What this parameter is for.

    Returns:
        Dictionary with the result structure.
    """
    # Check cache first
    cache_key = f"my_new_tool:{my_param}"
    cached = self._cache_get(cache_key)
    if cached is not None:
        return cached

    # Make API call
    data = await self._request("GET", f"/repos/{self.owner}/{self.repo}/...")

    # Process and cache
    result = {"key": data["value"]}
    self._cache_set(cache_key, result, ttl=3600)  # 1 hour

    return result
```

### Step 4: Add Tests

Create `./tests/test_my_new_tool.py`:

```python
import pytest
from ctm_mcp_server.data.github_client import GitHubClient

class TestMyNewTool:
    @pytest.fixture
    def client(self) -> GitHubClient:
        return GitHubClient(owner="octocat", repo="Hello-World")

    @pytest.mark.asyncio
    async def test_basic_functionality(self, client: GitHubClient) -> None:
        result = await client.my_new_method("test_param")
        assert result is not None
        assert "key" in result
```

### Step 5: Update Documentation

1. Add to tool table in `ctm_mcp_server/README.md`
2. Add to CLAUDE.md if it's a commonly used tool
3. If adding to VS Code extension, add to `CORE_TOOLS` in `constants.ts`

---

## Testing Strategy

### Python Tests (MCP Server)

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=ctm_mcp_server --cov-report=html

# Run specific test file
uv run pytest tests/test_parser.py -v

# Run tests matching pattern
uv run pytest -k "test_github" -v

# Run with verbose output
uv run pytest tests/ -v --tb=short
```

#### Test Categories

| File | Tests |
|------|-------|
| `test_parser.py` | Tree-sitter symbol extraction |
| `test_github_no_token.py` | GitHub API without authentication |

#### Writing Tests

```python
import pytest
from ctm_mcp_server.data.github_client import GitHubClient

class TestFeatureName:
    """Group related tests in a class."""

    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch) -> GitHubClient:
        """Fixture to create a client with controlled environment."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        return GitHubClient(owner="octocat", repo="Hello-World")

    @pytest.mark.asyncio
    async def test_something(self, client: GitHubClient) -> None:
        """Test description."""
        result = await client.some_method()
        assert result is not None
```

### TypeScript Tests (VS Code Extension)

```bash
cd extensions/vscode

# Run all tests
npm test

# Run specific test
npm test -- --grep "FactStore"

# Run with coverage
npm run test:coverage
```

#### Test Files

| File | Tests |
|------|-------|
| `factStore.test.ts` | Fact extraction and token optimization |
| `constants.test.ts` | Configuration constants |
| `providers/*.test.ts` | LLM provider adapters |
| `utils/github.test.ts` | GitHub URL parsing |

---

## Building & Distribution

### Building the Python Package

```bash
# Clean previous builds
rm -rf dist/                    # Linux/macOS
rmdir /s /q dist                # Windows

# Build wheel and source distribution
uv build

# Output (version will match pyproject.toml):
# dist/codebase_time_machine-<version>-py3-none-any.whl
# dist/codebase_time_machine-<version>.tar.gz
```

### Testing the Build Locally

```bash
# Create fresh test environment
python -m venv test_env
source test_env/bin/activate    # Linux/macOS
test_env\Scripts\activate       # Windows

# Install from local wheel (replace version with actual build version)
pip install dist/codebase_time_machine-<version>-py3-none-any.whl

# Test it works
python -c "import ctm_mcp_server; print('OK')"

# Cleanup
deactivate
rm -rf test_env                 # Linux/macOS
rmdir /s /q test_env            # Windows
```

### Building the VS Code Extension

```bash
cd extensions/vscode

# Make sure code is compiled first
npm run compile

# Create .vsix installer package
npm run package

# Output: codebase-time-machine-<version>.vsix
```

### Installing the Extension from VSIX

**In VS Code:**
1. Open Extensions view (`Ctrl+Shift+X` or `Cmd+Shift+X`)
2. Click `...` (More Actions) in the top-right
3. Select "Install from VSIX..."
4. Navigate to and select `codebase-time-machine-<version>.vsix`
5. Reload VS Code when prompted

**Command Line:**
```bash
code --install-extension codebase-time-machine-<version>.vsix
```

---

## Troubleshooting

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

### MCP server not found

```bash
# Verify server installation
pip list | grep codebase-time-machine

# Or for local development
uv run ctm-server --help
```

### Package installation fails

```bash
# Clear pip cache
pip cache purge

# Reinstall
pip uninstall codebase-time-machine
pip install codebase-time-machine
```

### "Cannot find module" errors (TypeScript)

```bash
cd extensions/vscode
rm -rf node_modules
npm install
npm run compile
```

### TypeScript compilation errors

```bash
# Check for syntax errors
npm run compile

# If types are wrong, update @types packages
npm update @types/vscode @types/node
```

### Extension crashes on activation

1. Check Output panel for error messages
2. Add try-catch around activation code
3. Test MCP server separately:
   ```bash
   python -m ctm_mcp_server.stdio_server --help
   ```

### Debugging Extension Code

1. Set breakpoints in TypeScript files
2. Press F5 to start debugging
3. Trigger the code path in Extension Development Host
4. Breakpoint hits in original VS Code window

### View Console Output

- **Debug Console**: View → Debug Console (in development window)
- **Output Panel**: View → Output → Select "Codebase Time Machine"
- **Developer Tools**: Help → Toggle Developer Tools

---

## Code Style

### Python

- **Formatter**: [Ruff](https://docs.astral.sh/ruff/) (line length: 100)
- **Linter**: [Ruff](https://docs.astral.sh/ruff/)
- **Type Checker**: [mypy](https://mypy.readthedocs.io/)

```bash
# Format
uv run ruff format ctm_mcp_server tests

# Lint
uv run ruff check ctm_mcp_server

# Type check
uv run mypy ctm_mcp_server --ignore-missing-imports
```

### TypeScript

- **Formatter/Linter**: ESLint + Prettier (via VS Code)
- **Compiler**: TypeScript strict mode

```bash
cd extensions/vscode
npm run lint
npm run compile
```

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Use Case |
|--------|----------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code change that neither fixes nor adds |
| `test:` | Adding or updating tests |
| `chore:` | Maintenance (deps, CI, etc.) |

Example:
```bash
git commit -m "feat: add trace_github_symbol_history tool"
git commit -m "fix: handle empty PR comments gracefully"
git commit -m "docs: update CONTRIBUTING.md with architecture details"
```

### Function Documentation

```python
async def get_line_context(
    self,
    file_path: str,
    line_start: int,
    line_end: int = None,
    history_depth: int = 1,
    include_discussions: bool = True,
) -> LineContextResult:
    """Get comprehensive context for specific lines of code.

    Aggregates blame, commit, PR, and issue information in a single call.
    This is the flagship tool for answering "Why does this code exist?"

    Args:
        file_path: Path to file relative to repo root.
        line_start: Starting line number (1-indexed).
        line_end: Ending line number (default: same as line_start).
        history_depth: Number of historical commits to analyze (default: 1).
            Use 5-10 for finding when code was originally introduced.
        include_discussions: Fetch PR/issue comments (slower but richer).

    Returns:
        LineContextResult with blame, commit, PR, and issue information.

    Raises:
        FileNotFoundError: If file doesn't exist at the specified ref.
        ValueError: If line numbers are out of range.
    """
```

---

## Commands Reference

### Python Package

| Command | Purpose |
|---------|---------|
| `uv sync` | Install/update dependencies |
| `uv run ctm-server` | Run server |
| `uv run python -m ctm_mcp_server.stdio_server` | Run server (Windows-safe) |
| `uv run pytest` | Run tests |
| `uv run pytest --cov=ctm_mcp_server` | Run tests with coverage |
| `uv run ruff format .` | Format code |
| `uv run ruff check .` | Lint code |
| `uv run ruff check --fix .` | Auto-fix lint issues |
| `uv run mypy ctm_mcp_server` | Type check |
| `uv build` | Build package |

### VS Code Extension

| Command | Purpose |
|---------|---------|
| `npm install` | Install dependencies |
| `npm run compile` | Compile TypeScript → JavaScript |
| `npm run watch` | Auto-compile on file changes |
| `npm run lint` | Check code style |
| `npm test` | Run tests |
| `npm run package` | Create .vsix installer |
| `F5` in VS Code | Debug extension |
| `Ctrl+R` in dev host | Reload extension |

### Git

| Command | Purpose |
|---------|---------|
| `git status` | Check status |
| `git diff` | See changes |
| `git log --oneline` | View commit history |
| `git checkout -b branch-name` | Create new branch |
| `git push -u origin branch-name` | Push branch to remote |
| `gh pr create` | Create pull request (GitHub CLI) |

---

## Questions?

- **Issues**: [GitHub Issues](https://github.com/BurakKTopal/codebase-time-machine/issues)
- **Discussions**: Open an issue for questions or feature requests
- **MCP Documentation**: https://modelcontextprotocol.io/
- **VS Code Extension API**: https://code.visualstudio.com/api
