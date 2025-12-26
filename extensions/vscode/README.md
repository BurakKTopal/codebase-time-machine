# Codebase Time Machine - VS Code Extension

Understand why code exists, not just what it does.

Select code, right-click, and get explanations including commit context, PR discussions, linked issues, and the decision chain behind the code.

## Features

- Right-click any code and select "CTM: Why does this code exist?"
- Get explanations including:
  - Who wrote the code and when
  - The commit that introduced it
  - Pull request discussions and reviews
  - Related issues and bug reports
  - The decision chain behind the code
- Multi-provider support: Anthropic Claude, OpenAI, or Google Gemini
- Follow-up questions: ask clarifying questions about the investigation
- Continue investigation: dig deeper if initial analysis is not enough

## Prerequisites

### 1. Codebase Time Machine Server

**From Test PyPI:**

```bash
# Option A: pip
pip install -i https://test.pypi.org/simple/ codebase-time-machine

# Option B: pipx (isolated)
pipx install -i https://test.pypi.org/simple/ codebase-time-machine
```

The extension uses the installed package by default.

**From source (for development):**

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# Clone repository
git clone https://github.com/burakktopal/codebase-time-machine.git
cd codebase-time-machine
uv sync

# Configure VS Code settings:
# ctm.serverPath: "/absolute/path/to/codebase-time-machine"
```

### 2. Python

Python 3.8 or higher. Check with:
```bash
python --version
```

### 3. Git

Git must be installed and available in your PATH.

### 4. API Key (Required)

You need an API key from one of these providers:

| Provider | Get API Key | Models |
|----------|-------------|--------|
| Anthropic | https://console.anthropic.com/ | Claude Haiku 3.5, Sonnet 4, Opus 4 |
| OpenAI | https://platform.openai.com/api-keys | GPT-4.1 Nano, GPT-4.1, o1 |
| Google | https://aistudio.google.com/apikey | Gemini 2.0 Flash-Lite, 2.5 Flash, 2.5 Pro |

### 5. GitHub Token (Optional)

For private repositories and higher API rate limits:
1. Go to https://github.com/settings/tokens
2. Generate a new token with `repo` scope
3. Add it to the extension settings

## Installation

### From VSIX file

1. Download `codebase-time-machine-0.1.0.vsix`
2. In VS Code: Extensions (Ctrl+Shift+X) > ... > Install from VSIX...
3. Select the downloaded file

### From Marketplace

Coming soon.

## Configuration

Open VS Code Settings (Ctrl+, or Cmd+,) and search for "CTM".

### Required Settings

| Setting | Description |
|---------|-------------|
| `ctm.apiKey` | Your API key for the selected provider |
| `ctm.provider` | Provider: `anthropic`, `openai`, or `gemini` |

### Optional Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ctm.model` | `claude-3-5-haiku-20241022` | Model ID (must match your provider) |
| `ctm.maxToolCalls` | `12` | Max tool calls per investigation (3-25) |
| `ctm.serverPath` | (empty) | Empty = use pip/pipx package. Set path = use local repo with uv |
| `ctm.serverCommand` | `python` | Override server command |
| `ctm.serverArgs` | `["-m", "ctm_mcp_server.stdio_server"]` | Override server args |
| `ctm.githubToken` | (empty) | GitHub token for private repos |

### Available Models

**Anthropic:**
- `claude-3-5-haiku-20241022` - Fast, cheapest
- `claude-sonnet-4-5-20250514` - Balanced
- `claude-opus-4-5-20250514` - Most capable

**OpenAI:**
- `gpt-4.1-nano` - Fastest, cheapest
- `gpt-4.1` - Balanced
- `o1` - Advanced reasoning

**Google Gemini:**
- `gemini-2.0-flash-lite` - Fastest, cheapest
- `gemini-2.5-flash` - Balanced
- `gemini-2.5-pro` - Most capable

## Usage

1. Open a file in a Git repository with a GitHub remote
2. Select 1-10 lines of code you want to understand
3. Right-click and select "CTM: Why does this code exist?"
4. View the analysis in the side panel

### Panel Features

- Summary: explanation of why the code exists
- Follow-up questions: ask clarifying questions
- Continue investigation: if the initial analysis is not complete
- Commands: type `/model` to change the model

## Quick Setup

```bash
# 1. Install CTM server
pip install -i https://test.pypi.org/simple/ codebase-time-machine

# 2. Install VS Code extension (from VSIX)

# 3. Configure in VS Code settings:
#    ctm.apiKey: your-api-key-here
#    ctm.provider: anthropic (or openai/gemini)
#    ctm.githubToken: your-github-token (optional)
```

## Troubleshooting

### "Failed to start CTM server"

1. Verify the package is installed:
   ```bash
   ctm-server --version
   ```
2. If using local development, verify uv is installed:
   ```bash
   uv --version
   ```
3. Set `ctm.serverPath` in VS Code settings to the CTM repository path

### "Cannot detect GitHub repo"

The extension only works with GitHub repositories. Verify your repo has a GitHub remote:
```bash
git remote -v
# Should show github.com in the URL
```

### "API key not configured"

Open Settings, search "ctm.apiKey", and paste your API key. Make sure `ctm.provider` matches your API key provider.

### "File has uncommitted changes"

The extension uses git blame which shows committed code. Either commit your changes or click "Continue Anyway".

### Rate Limits / Slow Responses

- Add a GitHub token in `ctm.githubToken` for higher API limits
- Use a faster model like `claude-3-5-haiku`
- Reduce `ctm.maxToolCalls` if investigations are slow

## How It Works

1. You select code in VS Code
2. Extension detects the GitHub repository
3. CTM server starts and provides 35 code investigation tools
4. The model investigates using git blame, PR history, and issue tracking
5. Results displayed with the decision chain

The extension uses the Model Context Protocol (MCP) to communicate with the CTM server.

## Privacy

- Your code is sent to the provider you select (Anthropic/OpenAI/Google)
- GitHub API calls are made to fetch PR/issue context
- No data is stored by the extension beyond your VS Code session
- API keys are stored in VS Code settings

## License

AGPL-3.0. See [LICENSE](LICENSE) for details.

## Issues

Report issues at: https://github.com/burakktopal/codebase-time-machine/issues
