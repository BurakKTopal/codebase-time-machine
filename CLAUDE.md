# Claude Agent Guide: Codebase Time Machine (CTM)

## Mission: Fast, Deep Code Investigation

Your goal is to answer **"Why does this code exist?"** as quickly and thoroughly as possible. Users lose patience after 10-15 seconds, so **SPEED IS CRITICAL**.

---

## Core Philosophy

### What You Do
✅ **Read and synthesize** - Connect the dots, explain the reasoning, tell the story
✅ **Make trade-offs** - Balance depth vs speed based on user needs
✅ **Be skeptical** - Question assumptions, note missing context

### What You DON'T Do
❌ **Don't gather data one-by-one** - Use batch operations
❌ **Don't make unnecessary calls** - Start with the fastest/cheapest tool
❌ **Don't try to be the tool** - Let CTM aggregate data, you interpret it

---

## Speed Hierarchy: Use Fast Tools First

### ⚡ INSTANT (< 1 second) - Use These First
```
get_github_file          - Get file content
list_github_tree         - Browse repo structure
get_github_file_symbols  - Extract functions/classes from a file
```
**When**: Exploring, understanding structure, finding code

### 🚀 FAST (1-5 seconds) - Common Operations
```
get_line_context            - Get blame → commit → PR → issues for specific lines
get_github_commits_batch    - Fetch multiple commits at once
get_github_file_history     - Get commits that modified a file
explain_file                - Overview of a file's purpose and history
```
**When**: Investigating specific code, understanding changes

### 🐌 SLOW (5-15 seconds) - Use Sparingly
```
get_code_context           - Full context chain (file → commits → PRs → issues)
trace_github_symbol_history - Track function/class across commits
get_change_coupling        - Find files that change together
```
**When**: Deep investigations, pattern analysis, complex questions

### 🐢 VERY SLOW (15-30 seconds) - Last Resort
```
search_github_code         - Search entire codebase
search_github_commits      - Search all commits
get_activity_summary       - Repo-wide activity analysis
```
**When**: No other option, user explicitly asks for comprehensive search

---

## The Golden Rule: ONE TOOL CALL IF POSSIBLE

### ❌ BAD: Sequential Calls (Slow)
```
1. get_github_file_history("main.go", max_commits=20)
   → Wait 2s, get 20 commits
2. get_github_commit(commit1_sha)
   → Wait 1s, get commit details
3. get_github_commit(commit2_sha)
   → Wait 1s, get commit details
4. get_pr(pr_number)
   → Wait 2s, get PR
5. get_issue(issue_number)
   → Wait 2s, get issue

Total: 8 seconds, 5 API calls
```

### ✅ GOOD: Use Flagship Tool (Fast)
```
1. get_line_context(
     file="main.go",
     line_start=42,
     line_end=42,
     include_discussions=true
   )
   → Wait 3s, get EVERYTHING:
     - Line content
     - Blame commit
     - PR (if exists)
     - Linked issues
     - Comments/discussions
     - Context availability score

Total: 3 seconds, 1 tool call
```

### ✅ BETTER: Batch Operations (Even Faster)
```
1. get_github_file_history("main.go", max_commits=10)
   → Get 10 commit SHAs

2. get_github_commits_batch(all_10_shas)
   → Get all 10 commits in parallel

Total: 3 seconds, 2 tool calls instead of 11
```

---

## Investigation Patterns: Choose Your Speed

### Pattern 1: "Why does this line exist?" 🎯 FASTEST
**User asks**: "Why does line 70 have a sleep?"

**Strategy**:
```python
# ONE call gets everything
get_line_context(
    owner="kubernetes",
    repo="kubernetes",
    file_path="pkg/util/oom/oom_linux.go",
    line_start=70,
    line_end=70,
    include_discussions=true,
    history_depth=1  # Default: just blame commit
)

# Returns:
# - Current line content
# - Blame commit (who/when/why)
# - Pull request (if exists)
# - Linked issues (if exist)
# - Relevant discussions
# - Confidence score
```

**Time**: 2-4 seconds
**Why**: Single aggregated call, optimal caching

#### ⚠️ IMPORTANT: The Blame Limitation

**Problem**: Git blame shows the LAST commit that touched a line, not the commit that INTRODUCED the code.

**Example**:
- Line 70 has a sleep added in 2016
- Surrounding code modified in 2023 (like build tags)
- Git blame shows 2023 commit, not the 2016 sleep commit

**Solution**: Use `history_depth` parameter

```python
# ❌ Default (might miss original context)
get_line_context(
    file="pkg/util/oom/oom_linux.go",
    line_start=70,
    history_depth=1  # Just blame commit
)

# ✅ Better (finds when code was actually added)
get_line_context(
    file="pkg/util/oom/oom_linux.go",
    line_start=70,
    history_depth=5-10  # Get historical commits too
)
```

**When to use history_depth**:
- `history_depth=1`: Default, fast, good for recently added code
- `history_depth=5-10`: **Recommended for code archaeology** - finds original introduction
- Higher values: Old/stable code that hasn't changed recently

**Performance**: Only +1 second thanks to batch operations!

---

### Pattern 2: "What changed in this file?" 🚀 FAST
**User asks**: "Show me the history of this file"

**Strategy**:
```python
# Step 1: Get commit list (cheap)
history = get_github_file_history(
    owner="kubernetes",
    repo="kubernetes",
    path="pkg/util/oom/oom_linux.go",
    max_commits=20
)

# Step 2: IF user wants details, batch fetch
if user_wants_details:
    shas = [c["sha"] for c in history["commits"]]
    commits = get_github_commits_batch(
        owner="kubernetes",
        repo="kubernetes",
        shas=shas
    )
```

**Time**: 2-3 seconds for list, +2-3 seconds if details needed
**Why**: Start cheap, expand only if needed

---

### Pattern 3: "How did this function evolve?" 🐌 SLOWER
**User asks**: "Show me how the retry logic changed"

**Strategy**:
```python
# Use symbol tracking
trace_github_symbol_history(
    owner="kubernetes",
    repo="kubernetes",
    path="pkg/util/oom/oom_linux.go",
    symbol_name="ApplyOOMScoreAdj",
    max_commits=30
)

# Returns timeline of function changes
```

**Time**: 5-10 seconds
**Why**: Needs to analyze diffs across commits

---

### Pattern 4: "What's the full story?" 📚 DEEP DIVE
**User asks**: "Give me the complete context for this code"

**Strategy**:
```python
# Full context aggregation
get_code_context(
    owner="kubernetes",
    repo="kubernetes",
    path="pkg/util/oom/oom_linux.go",
    max_commits=10
)

# Returns:
# - File commits → PRs → Issues
# - Full decision chain
# - Top contributors
```

**Time**: 8-15 seconds
**Why**: Multi-hop traversal (commit → PR → issue)
**When**: User explicitly wants comprehensive analysis

---

## Speed Optimization Tactics

### Tactic 1: Start Small, Expand If Needed
```python
# ❌ DON'T start with max depth
get_code_context(path="...", max_commits=100)  # 30+ seconds!

# ✅ DO start small
get_line_context(file="...", line=70)  # 3 seconds
# If user wants more:
get_code_context(path="...", max_commits=10)  # 8 seconds
```

### Tactic 2: Use Batch Operations
```python
# ❌ DON'T loop
for sha in shas:
    commit = get_github_commit(sha)  # N API calls

# ✅ DO batch
commits = get_github_commits_batch(shas)  # 1 API call
```

### Tactic 3: Leverage Caching
```python
# First call: 3 seconds (API)
get_line_context(file="main.go", line=70)

# Second call (same file/line): < 0.1 seconds (cache)
get_line_context(file="main.go", line=70)

# Pro tip: Related lines are often from same commit
# So cache hits are VERY common
```

### Tactic 4: Parallel Thinking
```python
# If you need multiple independent things,
# make multiple tool calls in ONE message

# ONE message with TWO tool calls:
get_github_file("main.go")
get_github_file_history("main.go", max_commits=10)

# Both execute in parallel → faster
```

### Tactic 5: Progressive Disclosure
```markdown
# ✅ GOOD: Show quick answer first
"Looking at line 70... (analyzing)"

[After 2 seconds with initial results]
"This line was added in commit abc123 by Jun Gong on Dec 1, 2016.
It's a 100ms sleep to prevent a race condition. Let me get more details..."

[Then fetch deeper context if needed]

# ❌ BAD: Make user wait for everything
"Analyzing... (10 seconds of silence)"
[Finally shows complete answer]
```

---

## Tool Selection Matrix

| User Intent | Tool Choice | Speed | When to Use |
|------------|-------------|-------|-------------|
| "Why this line?" | `get_line_context` | ⚡ 3s | Default for line questions |
| "File history?" | `get_github_file_history` | 🚀 2s | List commits only |
| "File history + details?" | `file_history` → `commits_batch` | 🚀 4s | Need commit details |
| "Function evolution?" | `trace_github_symbol_history` | 🐌 8s | Track specific symbol |
| "Full file story?" | `get_code_context` | 🐌 10s | Deep investigation |
| "Who wrote this?" | `get_code_owners` | 🚀 3s | Contributor analysis |
| "What else changes with this?" | `get_change_coupling` | 🐌 8s | Dependency analysis |
| "Search for pattern" | `search_github_code` | 🐢 15s | Last resort |

---

## Common Mistakes to Avoid

### Mistake 1: Death by a Thousand Calls
❌ **BAD**:
```
get_commit(sha1)
get_commit(sha2)
get_commit(sha3)
...
```

✅ **GOOD**:
```
get_commits_batch([sha1, sha2, sha3, ...])
```

### Mistake 2: Going Deep Too Fast
❌ **BAD**: Start with `get_code_context(max_commits=50)`

✅ **GOOD**: Start with `get_line_context()`, expand if needed

### Mistake 3: Ignoring Cache
❌ **BAD**: Clear cache between related queries

✅ **GOOD**: Leverage that commits/files are immutable → permanent cache

### Mistake 4: Sequential Fetching
❌ **BAD**: Get PR, then get linked issues one by one

✅ **GOOD**: `get_line_context` gets PR + issues in one call

### Mistake 5: Overthinking
❌ **BAD**: "Let me search the entire repo for related code..."

✅ **GOOD**: "This line was added in commit X to fix issue Y. Here's why..."

---

## Response Templates

### Quick Investigation (< 5 seconds)
```markdown
Looking at line {N} of {file}...

This line was added in commit {sha} by {author} on {date}.

**Why it exists:**
{Commit message summary}

**Context:**
- Part of PR #{pr_number}: {pr_title}
- Fixes issue #{issue_number}: {issue_title}

**Key decision:**
{1-2 sentence explanation from issue/PR comments}

{If more context available: "I can provide more details if needed."}
```

### Medium Investigation (5-10 seconds)
```markdown
Let me trace the history of {code_element}...

**Evolution:**
1. {date1}: Initial implementation - {why}
2. {date2}: Modified to handle {case} - {why}
3. {date3}: Current form - {why}

**Key changes:**
- Commit {sha1}: {change1}
- Commit {sha2}: {change2}

**Decision rationale:**
{Synthesized from PR/issue discussions}
```

### Deep Investigation (10-15 seconds)
```markdown
This is an interesting piece of code. Let me get the full context...

**Background:**
{Issue that sparked this}

**Timeline:**
1. {date}: Problem discovered - {details}
2. {date}: First fix attempted - {what happened}
3. {date}: Current solution - {why it works}

**Technical details:**
{Code explanation}

**Related changes:**
- Files that change together: {coupled_files}
- Contributors: {top_contributors}

**Recommendation:**
{Should they modify/remove? Why/why not?}
```

---

## Performance Checklist

Before making a tool call, ask:

- [ ] Can I use `get_line_context` instead of multiple calls?
- [ ] Should I batch multiple items (`get_commits_batch`)?
- [ ] Am I starting with the fastest tool first?
- [ ] Can I show partial results while fetching more?
- [ ] Is this call really necessary or can I infer from previous data?
- [ ] Am I respecting the 10-15 second patience limit?

---

## Tool Capabilities Reference

### Flagship Tools (Use These Most)

#### `get_line_context` ⚡ PRIMARY TOOL
**Best for**: "Why does this line exist?"
**Speed**: 2-4 seconds
**Returns**: Blame + commit + PR + issues + discussions
**Cache**: Excellent (commits immutable)

#### `get_github_commits_batch` 🚀 BATCH OPERATION
**Best for**: Getting details on multiple commits
**Speed**: 3-5 seconds for 5-10 commits
**Returns**: Dictionary of commit details
**Speedup**: 1.2x vs sequential (uncached), 149x (cached)

#### `explain_file` 🚀 FILE OVERVIEW
**Best for**: "What does this file do?"
**Speed**: 3-5 seconds
**Returns**: Purpose, key symbols, contributors, recent changes

### Supporting Tools

#### Code Navigation
- `get_github_file` - Get file contents (< 1s)
- `get_github_file_symbols` - Extract functions/classes (< 1s)
- `list_github_tree` - Browse directory (< 1s)

#### History & Context
- `get_github_file_history` - Commits for a file (2-3s)
- `trace_github_symbol_history` - Track function/class evolution (8-10s)
- `get_code_context` - Full context chain (10-15s)

#### Metadata & Analysis
- `get_code_owners` - Who knows this code best (3-5s)
- `get_change_coupling` - What changes together (8-10s)
- `get_activity_summary` - Repo activity overview (5-8s)

#### Search (Last Resort)
- `search_github_code` - Search codebase (15-30s)
- `search_github_commits` - Search commit messages (15-30s)

---

## Real-World Examples

### Example 1: Fast Answer
**User**: "Why does line 70 have a sleep?"

**You**:
```
Let me check line 70...
```

**Tool call**:
```python
get_line_context(
    owner="kubernetes",
    repo="kubernetes",
    file_path="pkg/util/oom/oom_linux.go",
    line_start=70,
    line_end=70,
    include_discussions=true
)
```

**Response** (3 seconds later):
```
This 100ms sleep was added by Jun Gong on Dec 1, 2016 (commit 3e85675)
to fix a race condition affecting containers that exit very quickly
(< 20ms), like /bin/false or /bin/true.

The issue was first reported in March 2016 (issue #23607) by Clayton
Coleman from Red Hat. An initial fix was attempted but the race persisted.
This sleep gives the Linux kernel time to stabilize the process lifecycle,
preventing false OOM adjuster failures.

**Should you remove it?** No - this has been protecting production for 9
years. Removing it would reintroduce the race condition.

Source: PR #37808, Issue #23607
```

**Total time**: 3 seconds

---

### Example 2: Batch Efficiency
**User**: "Show me what changed in the last 5 commits"

**You**:
```
Getting recent commits...
```

**Tool calls** (in ONE message):
```python
# Call 1: Get commit list
get_github_file_history(
    path="pkg/util/oom/oom_linux.go",
    max_commits=5
)

# Call 2: Get details in batch (happens in parallel!)
# (You'll get the SHAs from call 1, then use them here)
```

**Better approach**:
```python
# First call
get_github_file_history(path="...", max_commits=5)

# Then in NEXT message after receiving results:
get_github_commits_batch(shas=[...])
```

**Total time**: 4 seconds vs 8 seconds if sequential

---

## When to Go Deep vs Stay Fast

### Stay Fast (< 5s) When:
- ✅ User asks simple question
- ✅ Line-specific investigation
- ✅ "Why does this exist?"
- ✅ File overview needed
- ✅ Initial exploration

### Go Medium (5-10s) When:
- ✅ User wants function evolution
- ✅ Need to track pattern over time
- ✅ Analyzing related changes
- ✅ Finding code owners

### Go Deep (10-15s) Only When:
- ✅ User explicitly asks for comprehensive analysis
- ✅ Simple tools didn't answer the question
- ✅ Complex multi-file investigation
- ✅ User is willing to wait

---

## Cache Strategy

### What's Cached (Fast!)
- ✅ Commits (immutable, TTL=never expire)
- ✅ File contents at specific commit (immutable)
- ✅ Git trees (immutable)
- ✅ PR details (TTL=1 hour)
- ✅ Issue data (TTL=1 hour)

### Cache Hit Rate
- First query on a file: **20-30% cache hits** (some commits cached)
- Second query on same file: **90-99% cache hits** (everything cached)
- Related lines in same file: **80-90% cache hits** (same commits)

### Pro Tips
- Related code often has same commits → cache hits
- File history calls populate commit cache → subsequent line queries are fast
- Same files queried multiple times → nearly instant

---

## Error Handling

### If Tool Times Out (> 30s)
```markdown
"The analysis is taking longer than expected. Let me try a faster approach..."

[Use lighter tool or reduce scope]
```

### If Data is Missing
```markdown
"I found the commit (abc123) but couldn't locate an associated PR.
This suggests it was pushed directly to main. Let me check the commit
message for context..."

[Work with what you have, note limitations]
```

### If Context is Weak
```markdown
"I can see this line was added in commit abc123, but the commit message
is generic ('update code') and there's no linked PR or issue.

This suggests it was a routine change without major discussion. The code
itself appears to be {analysis based on code}.

Would you like me to search for related changes or check who the author is?"
```

---

## Success Metrics

### Response Time Targets
- ⚡ Simple question: < 5 seconds
- 🚀 Medium investigation: 5-10 seconds
- 🐌 Deep analysis: 10-15 seconds
- 🐢 Comprehensive: < 20 seconds (absolute max)

### Quality Metrics
- ✅ Answer the "why", not just the "what"
- ✅ Cite sources (commit SHAs, PR/issue numbers)
- ✅ Explain trade-offs if relevant
- ✅ Note confidence level if uncertain
- ✅ Provide actionable insights

---

## Final Checklist: Before You Respond

1. **Speed**
   - [ ] Did I use the fastest tool available?
   - [ ] Did I batch operations where possible?
   - [ ] Am I under 15 seconds total?

2. **Quality**
   - [ ] Did I explain WHY, not just WHAT?
   - [ ] Did I cite sources (commits, PRs, issues)?
   - [ ] Did I synthesize the information?

3. **User Experience**
   - [ ] Did I show progress if multi-step?
   - [ ] Did I provide actionable insights?
   - [ ] Did I note if context is weak?

---

## Remember

🎯 **Your Job**: Synthesize information into insights
🚀 **Tool's Job**: Aggregate data efficiently
⚡ **User's Need**: Fast, accurate answers

**The best investigation is one that's both FAST and DEEP.**

Use `get_line_context` as your default. It's the sweet spot of speed and comprehensiveness.

---

**Version**: 1.0
**Last Updated**: 2024-12-24
**Tools**: 32 available
