"""
Tree-sitter parser wrapper.

Provides a unified interface for parsing code in multiple languages.
"""

from pathlib import Path
from typing import Any

import tree_sitter_python
from tree_sitter import Language, Parser

from ctm_mcp_server.models.symbol_models import Symbol, SymbolType


class ParserError(Exception):
    """Base exception for parser errors."""

    pass


class CodeParser:
    """Multi-language code parser using tree-sitter."""

    # Supported languages and their file extensions
    LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
        "python": [".py", ".pyi"],
        # Future: add more languages
        # "javascript": [".js", ".jsx", ".mjs"],
        # "typescript": [".ts", ".tsx"],
        # "go": [".go"],
        # "rust": [".rs"],
    }

    def __init__(self) -> None:
        """Initialize the parser with language support."""
        self._parsers: dict[str, Parser] = {}
        self._languages: dict[str, Language] = {}
        self._init_languages()

    def _init_languages(self) -> None:
        """Initialize supported languages."""
        # Python
        self._languages["python"] = Language(tree_sitter_python.language())
        python_parser = Parser(self._languages["python"])
        self._parsers["python"] = python_parser

    def detect_language(self, file_path: str | Path) -> str | None:
        """Detect language from file extension.

        Args:
            file_path: Path to the file.

        Returns:
            Language name or None if not supported.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        for lang, extensions in self.LANGUAGE_EXTENSIONS.items():
            if suffix in extensions:
                return lang
        return None

    def parse(self, code: str, language: str) -> Any:
        """Parse source code.

        Args:
            code: Source code string.
            language: Language name.

        Returns:
            tree-sitter Tree object.

        Raises:
            ParserError: If language not supported.
        """
        if language not in self._parsers:
            raise ParserError(f"Unsupported language: {language}")

        parser = self._parsers[language]
        return parser.parse(code.encode("utf-8"))

    def extract_symbols(self, code: str, language: str) -> list[Symbol]:
        """Extract symbols from source code.

        Args:
            code: Source code string.
            language: Language name.

        Returns:
            List of Symbol objects.
        """
        tree = self.parse(code, language)

        if language == "python":
            return self._extract_python_symbols(tree, code)
        else:
            raise ParserError(f"Symbol extraction not implemented for: {language}")

    def _extract_python_symbols(self, tree: Any, code: str) -> list[Symbol]:
        """Extract symbols from Python code."""
        symbols: list[Symbol] = []

        def get_docstring(node: Any) -> str | None:
            """Extract docstring from a function/class body."""
            body = None
            for child in node.children:
                if child.type == "block":
                    body = child
                    break

            if body and body.children:
                first_stmt = body.children[0]
                if first_stmt.type == "expression_statement":
                    expr = first_stmt.children[0] if first_stmt.children else None
                    if expr and expr.type == "string":
                        docstring = code[expr.start_byte : expr.end_byte]
                        # Clean up docstring
                        docstring = docstring.strip("\"'")
                        if docstring.startswith('""'):
                            docstring = (
                                docstring[2:-2] if docstring.endswith('""') else docstring[2:]
                            )
                        return docstring.strip()
            return None

        def get_signature(node: Any) -> str | None:
            """Extract function signature."""
            if node.type != "function_definition":
                return None

            # Find parameters
            for child in node.children:
                if child.type == "parameters":
                    params = code[child.start_byte : child.end_byte]
                    name_node = None
                    for c in node.children:
                        if c.type == "identifier":
                            name_node = c
                            break
                    if name_node:
                        name = code[name_node.start_byte : name_node.end_byte]
                        return f"def {name}{params}"
            return None

        def get_decorators(node: Any) -> list[str]:
            """Extract decorators from a decorated definition."""
            decorators = []
            # Check if parent is decorated_definition
            if node.parent and node.parent.type == "decorated_definition":
                for child in node.parent.children:
                    if child.type == "decorator":
                        dec_text = code[child.start_byte : child.end_byte]
                        decorators.append(dec_text)
            return decorators

        def visit(node: Any, parent_name: str | None = None) -> None:
            """Recursively visit nodes."""
            if node.type == "function_definition":
                # Get function name
                name_node = None
                for child in node.children:
                    if child.type == "identifier":
                        name_node = child
                        break

                if name_node:
                    name = code[name_node.start_byte : name_node.end_byte]
                    full_name = f"{parent_name}.{name}" if parent_name else name

                    # Determine if it's a method
                    symbol_type = SymbolType.METHOD if parent_name else SymbolType.FUNCTION

                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=full_name,
                            type=symbol_type,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=get_signature(node),
                            docstring=get_docstring(node),
                            decorators=get_decorators(node),
                        )
                    )

            elif node.type == "class_definition":
                # Get class name
                name_node = None
                for child in node.children:
                    if child.type == "identifier":
                        name_node = child
                        break

                if name_node:
                    name = code[name_node.start_byte : name_node.end_byte]
                    full_name = f"{parent_name}.{name}" if parent_name else name

                    # Get base classes
                    bases: list[str] = []
                    for child in node.children:
                        if child.type == "argument_list":
                            bases_text = code[child.start_byte : child.end_byte]
                            bases = [b.strip() for b in bases_text[1:-1].split(",") if b.strip()]
                            break

                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=full_name,
                            type=SymbolType.CLASS,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            docstring=get_docstring(node),
                            decorators=get_decorators(node),
                            bases=bases,
                        )
                    )

                    # Visit children with class as parent
                    for child in node.children:
                        visit(child, full_name)
                    return  # Don't visit children again

            elif node.type == "decorated_definition":
                # The actual definition is a child
                for child in node.children:
                    if child.type in ("function_definition", "class_definition"):
                        visit(child, parent_name)
                return

            # Visit children
            for child in node.children:
                visit(child, parent_name)

        visit(tree.root_node)
        return symbols

    def extract_symbols_from_file(self, file_path: str | Path) -> list[Symbol]:
        """Extract symbols from a file.

        Args:
            file_path: Path to the source file.

        Returns:
            List of Symbol objects.

        Raises:
            ParserError: If file cannot be parsed.
        """
        path = Path(file_path)
        language = self.detect_language(path)

        if not language:
            raise ParserError(f"Unsupported file type: {path.suffix}")

        try:
            code = path.read_text(encoding="utf-8")
        except Exception as e:
            raise ParserError(f"Error reading file: {e}") from e

        return self.extract_symbols(code, language)
