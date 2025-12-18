"""
Codebase Time Machine - Data Models

Pydantic models for representing git objects, GitHub entities,
and tool results.
"""

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
from ctm_mcp_server.models.github_models import (
    Comment,
    Issue,
    Label,
    PullRequest,
    Review,
    User,
)
from ctm_mcp_server.models.result_models import (
    BaseResult,
    BlameWithContextResult,
    CommitResult,
    ExplainCommitResult,
    FileHistoryResult,
    RepoInfoResult,
)
from ctm_mcp_server.models.symbol_models import (
    FileSymbols,
    Symbol,
    SymbolChange,
    SymbolHistory,
    SymbolType,
)

__all__ = [
    # Git models
    "Author",
    "Branch",
    "Commit",
    "FileChange",
    "DiffHunk",
    "DiffFile",
    "BlameLine",
    "BlameResult",
    # GitHub models
    "User",
    "Label",
    "Comment",
    "Review",
    "Issue",
    "PullRequest",
    # Result models
    "BaseResult",
    "RepoInfoResult",
    "CommitResult",
    "FileHistoryResult",
    "ExplainCommitResult",
    "BlameWithContextResult",
    # Symbol models
    "Symbol",
    "SymbolType",
    "SymbolChange",
    "SymbolHistory",
    "FileSymbols",
]
