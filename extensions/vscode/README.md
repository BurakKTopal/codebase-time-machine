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

```bash
pip install codebase-time-machine
```

See [MCP Server README](../../ctm_mcp_server/README.md) for details.

### 2. API Key (Required)

| Provider | Get API Key | Models |
|----------|-------------|--------|
| Anthropic | https://console.anthropic.com/ | Claude Haiku 3.5, Sonnet 4, Opus 4 |
| OpenAI | https://platform.openai.com/api-keys | GPT-4.1 Nano, GPT-4.1, o1 |
| Google | https://aistudio.google.com/apikey | Gemini 2.0 Flash-Lite, 2.5 Flash, 2.5 Pro |

### 3. GitHub Token (Optional)

For private repositories: https://github.com/settings/tokens (needs `repo` scope)

## Installation

1. Install from [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=BurakKTopal.codebase-time-machine)
   - Or search "Codebase Time Machine" in VS Code Extensions (Ctrl+Shift+X)
2. Configure settings (see below)

## Configuration

Open VS Code Settings:
- **Keyboard**: `Ctrl+,` (Windows/Linux) or `Cmd+,` (Mac)
- **Menu**: File → Preferences → Settings
- **Command Palette**: `Ctrl+Shift+P` → "Preferences: Open Settings"

Search for "CTM" to find all extension settings.

| Setting | Default | Description |
|---------|---------|-------------|
| `ctm.apiKey` | (required) | Your API key for the selected provider |
| `ctm.provider` | `anthropic` | Provider: `anthropic`, `openai`, or `gemini` |
| `ctm.model` | `claude-3-5-haiku-20241022` | Model ID |
| `ctm.maxToolCalls` | `12` | Max tool calls per investigation (3-25) |
| `ctm.githubToken` | (empty) | GitHub token for private repos |

## Usage

1. Open a file in a Git repository with a GitHub remote
2. Select 1-10 lines of code
3. Right-click → "CTM: Why does this code exist?"
4. View analysis in the side panel

### Panel Features

- **Summary**: Explanation of why the code exists with clickable links to commits, PRs, and issues
- **Follow-up questions**: Ask clarifying questions about the investigation
- **Continue investigation**: Dig deeper if the initial analysis is not complete
- **Commands**: Type `/model` to change the model mid-conversation

---

## Architecture: Token-Efficient Investigation

The extension is carefully designed to maximize investigation quality while minimizing token usage and **API costs**.

### Problem: Cost and Context Limits

LLMs charge per token. A naive approach would:
- Send all 32 MCP tools (huge schema = more tokens = more cost)
- Accumulate all tool results in conversation history (grows unbounded)
- Result: **$0.50-$2.00+ per investigation** and potential context overflow

### Solution: Multi-Layer Optimization

```
┌─────────────────────────────────────────────────────────────────┐
│                    VS Code Extension                             │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────┐   │
│  │ Tool Pruning│──>│  FactStore  │──>│ State-Based Prompts │   │
│  │ (10 tools)  │   │ (extract +  │   │ (rebuilt each turn) │   │
│  │             │   │  discard)   │   │                     │   │
│  └─────────────┘   └─────────────┘   └─────────────────────┘   │
│         │                 │                    │                │
│         v                 v                    v                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              SYSTEM_PROMPT.md (Agent Guide)              │   │
│  │     Teaches LLM investigation patterns & best practices  │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                      MCP Server (32 tools)                       │
└─────────────────────────────────────────────────────────────────┘
```

### 1. Tool Pruning: 10 Core Tools

Instead of sending all 32 tool schemas, we curate 10 essential tools:

```typescript
CORE_TOOLS = [
    'get_local_line_context',   // Primary: blame + PR + issues in ONE call
    'get_pr',                   // Full PR details
    'get_issue',                // Full issue details
    'search_prs_for_commit',    // Find PR from commit
    'get_github_file_history',  // File commit history
    'get_github_commits_batch', // Efficient batch fetching
    'explain_file',             // File overview
    'get_commit_diff',          // See actual changes
    'pickaxe_search',           // Find code origin
    'get_code_owners',          // Who knows this code
]
```

**Impact**: ~70% reduction in tool schema tokens.

### 2. FactStore: Extract Facts, Discard Raw Data

Tool results can be huge (full PR with 50 comments = thousands of tokens). FactStore solves this:

```
Tool Result (2000 tokens)          Facts (50 tokens)
─────────────────────────────  →   ─────────────────────
{                                  - PR #123: "Fix race condition" by Alice
  "pr": {                          - PR reason: Race condition in worker...
    "number": 123,                 - Issue #456: "Worker crashes randomly"
    "title": "Fix race...",
    "body": "...(500 chars)...",
    "comments": [...50 items...],
    ...
  }
}
```

**How it works**:
1. Tool returns raw result with `code_sections` (grouped by last-touch commit)
2. Each section includes `origins` - per-line pickaxe results grouped by origin SHA. For long-lined sections, a uniform pickaxe grouping algorithm is realized to reduce latency.
3. **Pattern detection** identifies common cases (commented code with active alternatives, TODOs, stale fixes) and provides quick answers
4. FactStore extracts key facts (commit SHAs, PR titles, issue descriptions, per-line origins, detected patterns)
5. FactStore extracts evidence (emails, timestamps, URLs)
6. Raw result is discarded
7. Only compact facts are kept in context

**Per-line origin detection**: When you select multiple lines, CTM runs pickaxe for each line to find when it was truly introduced. Lines are grouped by origin SHA for efficiency.

**Pattern-based shortcuts**: When the tool detects a pattern (e.g., commented code with an active implementation below), it provides a `quick_answer` so the LLM can deliver faster, more accurate responses without over-investigating simple cases.

**Impact**: ~90% reduction in context accumulation.

### 3. State-Based Prompts (Not Accumulated Messages)

Traditional approach accumulates all messages:
```
[System] + [User] + [Assistant] + [Tool1] + [Assistant] + [Tool2] + ...
                                  ↑ grows unbounded
```

CTM rebuilds the prompt each iteration:
```
[System] + [Current State Summary] + [Facts So Far] + [What To Do Next]
          ↑ constant size
```

**Impact**: Context usage stays flat regardless of investigation length.

### 4. Investigation Phases

The agent operates in two phases with different behaviors:

| Phase | Tool Calls | Behavior |
|-------|------------|----------|
| **Investigate** | 1 to ~75% of budget | Gather facts, follow leads, dig deeper |
| **Synthesize** | ~75% to 100% | Stop calling tools, write final answer |

The synthesis threshold is configurable via `ctm.maxToolCalls`:
- Default: 12 tool calls → synthesize at call 9
- If user sets 20 → synthesize at call 15

### 5. SYSTEM_PROMPT.md: Agent Training

The extension includes a carefully crafted system prompt that teaches the LLM:

- **Investigation patterns**: Start with `get_local_line_context`, follow PRs, check issues
- **Origin vs Last-Modified**: Blame shows last touch, use pickaxe for true origin
- **Hyperlink requirements**: Every commit/PR/issue must be clickable
- **Response structure**: What/When, Why, How, Context, Recommendation
- **Multi-section handling**: When selected code spans multiple commits

**Location**: `extensions/vscode/src/SYSTEM_PROMPT.md`

### Cost and Performance Comparison

| Approach | Tokens | Cost | Problem |
|----------|--------|------|---------|
| **Naive** (all tools + full accumulation) | 400k-500k | $0.50-$2.00+ | Expensive, context overflow |
| **Window pruning** (last N messages) | 100k-150k | $0.15-$0.30 | Agent loses critical context |
| **CTM Design** (FactStore + tool pruning) | **20k-40k** | **< $0.05** | Fast, thorough, cheap |

**Result**: A full investigation with follow-up questions costs **less than 5 cents** using Claude Haiku.

---

## Troubleshooting

### "Failed to start CTM server"
```bash
python -c "import ctm_mcp_server; print('OK')"
```

### "Cannot detect GitHub repo"
```bash
git remote -v  # Should show github.com
```

### "API key not configured"
Open Settings (`Ctrl+,`) → search "ctm.apiKey" → paste your key.

### Slow Responses
- Use `claude-3-5-haiku` (fastest)
- Reduce `ctm.maxToolCalls`
- Add GitHub token for higher rate limits

## Privacy & Data Storage

- **LLM Provider**: Selected code is sent to Anthropic/OpenAI/Google for analysis
- **GitHub API**: Calls are made to fetch PR/issue context
- **Extension**: No data stored beyond your VS Code session
- **MCP Server**: Caches GitHub API responses locally at `~/.ctm/cache.db` (SQLite) to reduce API calls and improve speed
- **API Keys**: Stored in VS Code settings

## License

AGPL-3.0. See [LICENSE](LICENSE).

## Issues

Report at: https://github.com/BurakKTopal/codebase-time-machine/issues
