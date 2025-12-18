"""
Code parsing module using tree-sitter.

Provides language-agnostic symbol extraction from source code.
"""

from ctm_mcp_server.parsing.parser import CodeParser, ParserError

__all__ = ["CodeParser", "ParserError"]
