"""
Symbol-related data models.

These models represent code symbols like functions, classes, and variables.
"""

from enum import Enum

from pydantic import BaseModel, Field


class SymbolType(str, Enum):
    """Type of code symbol."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    VARIABLE = "variable"
    CONSTANT = "constant"
    MODULE = "module"
    IMPORT = "import"
    PROPERTY = "property"
    PARAMETER = "parameter"


class Symbol(BaseModel):
    """Represents a code symbol (function, class, etc.)."""

    name: str = Field(description="Symbol name")
    qualified_name: str = Field(description="Fully qualified name (e.g., ClassName.method_name)")
    type: SymbolType
    start_line: int = Field(description="Starting line number (1-indexed)")
    end_line: int = Field(description="Ending line number (1-indexed)")

    # Optional metadata
    signature: str | None = Field(default=None, description="Function/method signature")
    docstring: str | None = Field(default=None, description="Documentation string")
    decorators: list[str] = Field(default_factory=list, description="Applied decorators")
    bases: list[str] = Field(default_factory=list, description="Base classes (for classes)")

    @property
    def line_count(self) -> int:
        """Number of lines this symbol spans."""
        return self.end_line - self.start_line + 1


class SymbolChange(BaseModel):
    """Represents a change to a symbol across commits."""

    commit_sha: str
    commit_short_sha: str
    commit_message: str
    commit_date: str
    author: str

    # Change details
    change_type: str = Field(description="Type of change: added, modified, deleted, renamed")
    old_start_line: int | None = None
    old_end_line: int | None = None
    new_start_line: int | None = None
    new_end_line: int | None = None

    # Content changes
    lines_added: int = 0
    lines_removed: int = 0

    # Links
    pr_number: int | None = None


class SymbolHistory(BaseModel):
    """History of a symbol across commits."""

    symbol_name: str
    qualified_name: str
    symbol_type: SymbolType
    file_path: str

    # Current state
    current_start_line: int | None = None
    current_end_line: int | None = None
    current_signature: str | None = None

    # History
    changes: list[SymbolChange] = Field(default_factory=list)
    total_commits: int = 0

    # Derived stats
    first_seen_commit: str | None = None
    first_seen_date: str | None = None
    last_modified_commit: str | None = None
    last_modified_date: str | None = None


class FileSymbols(BaseModel):
    """All symbols in a file."""

    file_path: str
    language: str
    symbols: list[Symbol] = Field(default_factory=list)

    @property
    def functions(self) -> list[Symbol]:
        """Get all functions."""
        return [s for s in self.symbols if s.type == SymbolType.FUNCTION]

    @property
    def methods(self) -> list[Symbol]:
        """Get all methods."""
        return [s for s in self.symbols if s.type == SymbolType.METHOD]

    @property
    def classes(self) -> list[Symbol]:
        """Get all classes."""
        return [s for s in self.symbols if s.type == SymbolType.CLASS]
