# Codebase Time Machine - VS Code Extension

Understand **why** code exists, not just what it does.

Select any code, right-click, and get AI-powered explanations including commit context, PR discussions, linked issues, and the full decision chain behind the code.

## Features

- **Right-click any code** and select "CTM: Why does this code exist?"
- Get instant AI-powered explanations including:
  - Who wrote the code and when
  - The commit that introduced it
  - Pull Request discussions and reviews
  - Related issues and bug reports
  - The full decision chain behind the code
- **Multi-provider support**: Choose between Anthropic Claude, OpenAI GPT, or Google Gemini
- **Follow-up questions**: Ask clarifying questions about the investigation
- **Continue investigation**: Dig deeper if initial analysis isn't enough

---

## Prerequisites

Before installing the extension, you need:

### 1. Codebase Time Machine Server

**Recommended: Install from PyPI (no uv required)**

```bash
# Option A: pip (simplest)
pip install codebase-time-machine

# Option B: pipx (isolated)
pipx install codebase-time-machine
```

The extension uses the installed package by default (`python -m ctm_mcp_server.stdio_server`).

**For Local Development Only**

If you're contributing to CTM development:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# or
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# Clone repository
git clone https://github.com/burakktopal/codebase-time-machine.git
cd codebase-time-machine
uv sync

# Configure VS Code settings:
# ctm.serverPath: "/absolute/path/to/codebase-time-machine"
#
# Note: Extension auto-detects local repo and runs via uv automatically.
# No need to manually configure serverCommand or serverArgs.
```

**Summary**:
- ✅ **Most users**: Install with pip/pipx (default configuration)
- 🛠️ **Developers**: Use local repo with uv (requires manual configuration)

### 2. Python

You need Python 3.8 or higher. Check with:
```bash
python --version
```

### 3. Git

Git must be installed and available in your PATH.
- **Windows**: https://git-scm.com/download/win
- **macOS**: `xcode-select --install`
- **Linux**: `sudo apt install git` (or equivalent)

### 4. API Key (Required)

You need an API key from one of these providers:

| Provider | Get API Key | Models Available |
|----------|-------------|------------------|
| **Anthropic** | https://console.anthropic.com/ | Claude Haiku 3.5, Sonnet 4.5, Opus 4.5 |
| **OpenAI** | https://platform.openai.com/api-keys | GPT-4.1 Nano, GPT-4.1, o1 |
| **Google** | https://aistudio.google.com/apikey | Gemini 2.0 Flash-Lite, 2.5 Flash, 3 Pro |

### 5. GitHub Token (Optional but Recommended)

For private repositories and higher API rate limits:
1. Go to https://github.com/settings/tokens
2. Generate a new token with `repo` scope
3. Add it to the extension settings

---

## Installation

### Option A: Install from VSIX file

1. Download `codebase-time-machine-0.1.0.vsix`
2. In VS Code: **Extensions** (Ctrl+Shift+X) → **...** → **Install from VSIX...**
3. Select the downloaded file

### Option B: Install from Marketplace

*(Coming soon)*

---

## Configuration

Open VS Code Settings (Ctrl+, or Cmd+,) and search for "CTM":

### Required Settings

| Setting | Description |
|---------|-------------|
| `ctm.apiKey` | Your API key for the selected provider |
| `ctm.provider` | AI provider: `anthropic`, `openai`, or `gemini` |

### Optional Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ctm.model` | `claude-3-5-haiku-20241022` | Model ID (must match your provider) |
| `ctm.maxToolCalls` | `12` | Max tool calls per investigation (3-25) |
| `ctm.serverPath` | *(empty)* | **Empty** = use pip/pipx package (recommended). **Set path** = use local repo with uv for development |
| `ctm.serverCommand` | `python` | Advanced: Override server command (auto-detected by default) |
| `ctm.serverArgs` | `["-m", "ctm_mcp_server.stdio_server"]` | Advanced: Override server args (auto-detected by default) |
| `ctm.githubToken` | *(empty)* | GitHub token for private repos |

### Available Models

**Anthropic:**
- `claude-3-5-haiku-20241022` - Fast, cheapest ($0.80/$4)
- `claude-sonnet-4-5-20250929` - Balanced ($3/$15)
- `claude-opus-4-5-20251101` - Most capable ($15/$75)

**OpenAI:**
- `gpt-4.1-nano` - Fastest, cheapest ($0.10/$0.40)
- `gpt-4.1` - Balanced, great for coding ($2/$8)
- `o1` - Advanced reasoning

**Google Gemini:**
- `gemini-2.0-flash-lite` - Fastest, cheapest ($0.075/$0.30)
- `gemini-2.5-flash` - Balanced with thinking ($0.15/$0.60)
- `gemini-3-pro` - Most powerful

---

## Usage

1. **Open a file** in a Git repository with a GitHub remote
2. **Select 1-10 lines** of code you want to understand
3. **Right-click** and select **"CTM: Why does this code exist?"**
4. **View the analysis** in the side panel

### Panel Features

- **Summary**: AI-generated explanation of why the code exists
- **Follow-up questions**: Ask clarifying questions
- **Continue investigation**: If the initial analysis isn't complete
- **Commands**: Type `/model` to change the AI model

---

## Quick Setup Example

### For End Users (Recommended)

```bash
# 1. Install CTM server
pip install codebase-time-machine

# 2. Install VS Code extension (from VSIX or Marketplace)

# 3. Configure in VS Code settings:
#    - ctm.apiKey: your-api-key-here
#    - ctm.provider: anthropic (or openai/gemini)
#    - ctm.githubToken: your-github-token (optional)

# Done! Extension uses default settings to run the package.
```

### For Local Development

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and set up CTM
git clone https://github.com/burakktopal/codebase-time-machine.git
cd codebase-time-machine
uv sync

# 3. Install VS Code extension

# 4. Configure in VS Code settings:
#    - ctm.apiKey: your-api-key
#    - ctm.provider: anthropic (or openai/gemini)
#    - ctm.serverPath: /absolute/path/to/codebase-time-machine
#
# The extension auto-detects local repo and uses uv automatically.
# You can manually override serverCommand/serverArgs if needed (advanced).
```

---

## Troubleshooting

### "Failed to start CTM server"

1. Verify `uv` is installed:
   ```bash
   uv --version
   ```
2. Verify CTM is set up:
   ```bash
   cd /path/to/codebase-time-machine
   uv run ctm-server --help
   ```
3. Set `ctm.serverPath` in VS Code settings to the CTM repository path

### "Cannot detect GitHub repo"

- The extension only works with GitHub repositories
- Verify your repo has a GitHub remote:
  ```bash
  git remote -v
  # Should show github.com in the URL
  ```

### "API key not configured"

- Open Settings → search "ctm.apiKey" → paste your API key
- Make sure `ctm.provider` matches your API key provider

### "File has uncommitted changes"

- The extension uses `git blame` which shows committed code
- Either commit your changes or click "Continue Anyway"

### Rate Limits / Slow Responses

- Add a GitHub token in `ctm.githubToken` for higher API limits
- Use a faster model like `claude-3-5-haiku` or `gpt-4o-mini`
- Reduce `ctm.maxToolCalls` if investigations are too slow

---

## How It Works

1. **You select code** in VS Code
2. **Extension detects** the GitHub repository
3. **MCP server starts** and provides code archaeology tools
4. **AI agent investigates** using git blame, PR history, and issue tracking
5. **Results displayed** with the full decision chain

The extension uses the Model Context Protocol (MCP) to communicate with the CTM server, which provides 30+ tools for code archaeology including:
- Git blame and commit history
- Pull request context and discussions
- Issue tracking and linked problems
- Code ownership analysis
- Change coupling detection

---

## Privacy & Security

- Your code is sent to the AI provider you select (Anthropic/OpenAI/Google)
- GitHub API calls are made to fetch PR/issue context
- No data is stored by the extension beyond your VS Code session
- API keys are stored in VS Code's settings (consider using secrets management)

---

## License

MIT

---

## Feedback & Issues

Report issues at: https://github.com/burak/codebase-time-machine/issues
