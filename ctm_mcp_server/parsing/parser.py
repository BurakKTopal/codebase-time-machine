"""
Tree-sitter parser wrapper.

Provides a unified interface for parsing code in multiple languages.
"""

from pathlib import Path
from typing import Any

import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_go
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_rust
import tree_sitter_typescript
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
        "javascript": [".js", ".jsx", ".mjs", ".cjs"],
        "typescript": [".ts", ".tsx"],
        "go": [".go"],
        "rust": [".rs"],
        "c": [".c", ".h"],
        "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".C"],
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
        self._parsers["python"] = Parser(self._languages["python"])

        # JavaScript
        self._languages["javascript"] = Language(tree_sitter_javascript.language())
        self._parsers["javascript"] = Parser(self._languages["javascript"])

        # TypeScript
        self._languages["typescript"] = Language(tree_sitter_typescript.language_typescript())
        self._parsers["typescript"] = Parser(self._languages["typescript"])

        # Go
        self._languages["go"] = Language(tree_sitter_go.language())
        self._parsers["go"] = Parser(self._languages["go"])

        # Rust
        self._languages["rust"] = Language(tree_sitter_rust.language())
        self._parsers["rust"] = Parser(self._languages["rust"])

        # C
        self._languages["c"] = Language(tree_sitter_c.language())
        self._parsers["c"] = Parser(self._languages["c"])

        # C++
        self._languages["cpp"] = Language(tree_sitter_cpp.language())
        self._parsers["cpp"] = Parser(self._languages["cpp"])

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
        elif language in ("javascript", "typescript"):
            return self._extract_js_ts_symbols(tree, code, language)
        elif language == "go":
            return self._extract_go_symbols(tree, code)
        elif language == "rust":
            return self._extract_rust_symbols(tree, code)
        elif language == "c":
            return self._extract_c_symbols(tree, code)
        elif language == "cpp":
            return self._extract_cpp_symbols(tree, code)
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

    def _extract_js_ts_symbols(self, tree: Any, code: str, language: str) -> list[Symbol]:
        """Extract symbols from JavaScript/TypeScript code."""
        symbols: list[Symbol] = []

        def get_function_signature(node: Any) -> str | None:
            """Extract function signature."""
            # Get function name
            name = None
            for child in node.children:
                if child.type == "identifier":
                    name = code[child.start_byte : child.end_byte]
                    break

            # Get parameters
            params = None
            for child in node.children:
                if child.type in ("formal_parameters", "parameters"):
                    params = code[child.start_byte : child.end_byte]
                    break

            if name and params:
                return f"function {name}{params}"
            return None

        def get_class_name(node: Any) -> str | None:
            """Extract class name."""
            for child in node.children:
                if child.type in ("identifier", "type_identifier"):
                    return code[child.start_byte : child.end_byte]
            return None

        def visit(
            node: Any, parent_name: str | None = None, parent_type: str | None = None
        ) -> None:
            """Recursively visit nodes."""
            # Function declarations and expressions
            if node.type in (
                "function_declaration",
                "function",
                "arrow_function",
                "method_definition",
            ):
                # Get function name
                name = None
                for child in node.children:
                    if child.type in ("identifier", "property_identifier"):
                        name = code[child.start_byte : child.end_byte]
                        break

                # Arrow functions might not have a name
                if not name and node.type == "arrow_function":
                    # Try to get name from parent variable declarator
                    if node.parent and node.parent.type == "variable_declarator":
                        for child in node.parent.children:
                            if child.type == "identifier":
                                name = code[child.start_byte : child.end_byte]
                                break

                if name:
                    full_name = f"{parent_name}.{name}" if parent_name else name

                    # Determine if it's a method or function
                    is_method = parent_type == "class" or node.type == "method_definition"
                    symbol_type = SymbolType.METHOD if is_method else SymbolType.FUNCTION

                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=full_name,
                            type=symbol_type,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=get_function_signature(node),
                        )
                    )

            # Class declarations
            elif node.type in ("class_declaration", "class"):
                name = get_class_name(node)

                if name:
                    full_name = f"{parent_name}.{name}" if parent_name else name

                    # Get base class (extends)
                    bases: list[str] = []
                    for child in node.children:
                        if child.type == "class_heritage":
                            for subchild in child.children:
                                if subchild.type == "identifier":
                                    bases.append(code[subchild.start_byte : subchild.end_byte])

                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=full_name,
                            type=SymbolType.CLASS,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            bases=bases,
                        )
                    )

                    # Visit children with class as parent
                    for child in node.children:
                        if child.type == "class_body":
                            for method in child.children:
                                visit(method, full_name, "class")
                    return

            # Visit children
            for child in node.children:
                visit(child, parent_name, parent_type)

        visit(tree.root_node)
        return symbols

    def _extract_go_symbols(self, tree: Any, code: str) -> list[Symbol]:
        """Extract symbols from Go code."""
        symbols: list[Symbol] = []

        def visit(node: Any, parent_name: str | None = None) -> None:
            """Recursively visit nodes."""
            # Function declarations
            if node.type == "function_declaration":
                name = None
                for child in node.children:
                    if child.type == "identifier":
                        name = code[child.start_byte : child.end_byte]
                        break

                if name:
                    full_name = f"{parent_name}.{name}" if parent_name else name
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=full_name,
                            type=SymbolType.FUNCTION,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                    )

            # Method declarations
            elif node.type == "method_declaration":
                name = None
                receiver = None
                for child in node.children:
                    if child.type == "field_identifier":
                        name = code[child.start_byte : child.end_byte]
                    elif child.type == "parameter_list" and not receiver:
                        # First parameter_list is receiver
                        receiver = code[child.start_byte : child.end_byte]

                if name:
                    full_name = f"{receiver}.{name}" if receiver else name
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=full_name,
                            type=SymbolType.METHOD,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                    )

            # Type declarations (structs, interfaces)
            elif node.type == "type_declaration":
                for child in node.children:
                    if child.type == "type_spec":
                        name = None
                        for spec_child in child.children:
                            if spec_child.type == "type_identifier":
                                name = code[spec_child.start_byte : spec_child.end_byte]
                                break

                        if name:
                            symbols.append(
                                Symbol(
                                    name=name,
                                    qualified_name=name,
                                    type=SymbolType.CLASS,  # Using CLASS for structs/interfaces
                                    start_line=child.start_point[0] + 1,
                                    end_line=child.end_point[0] + 1,
                                )
                            )

            # Visit children
            for child in node.children:
                visit(child, parent_name)

        visit(tree.root_node)
        return symbols

    def _extract_rust_symbols(self, tree: Any, code: str) -> list[Symbol]:
        """Extract symbols from Rust code."""
        symbols: list[Symbol] = []

        def visit(node: Any, parent_name: str | None = None) -> None:
            """Recursively visit nodes."""
            # Function items
            if node.type == "function_item":
                name = None
                for child in node.children:
                    if child.type == "identifier":
                        name = code[child.start_byte : child.end_byte]
                        break

                if name:
                    full_name = f"{parent_name}.{name}" if parent_name else name
                    # Check if it's a method (has self parameter)
                    is_method = parent_name is not None
                    symbol_type = SymbolType.METHOD if is_method else SymbolType.FUNCTION

                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=full_name,
                            type=symbol_type,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                    )

            # Struct, enum, trait declarations
            elif node.type in ("struct_item", "enum_item", "trait_item"):
                name = None
                for child in node.children:
                    if child.type == "type_identifier":
                        name = code[child.start_byte : child.end_byte]
                        break

                if name:
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=name,
                            type=SymbolType.CLASS,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                    )

                    # Visit impl blocks for this type
                    for child in node.children:
                        visit(child, name)

            # Impl blocks
            elif node.type == "impl_item":
                # Get type being implemented
                type_name = None
                for child in node.children:
                    if child.type == "type_identifier":
                        type_name = code[child.start_byte : child.end_byte]
                        break

                # Visit methods in impl block
                for child in node.children:
                    if child.type == "declaration_list":
                        for method in child.children:
                            visit(method, type_name)
                return

            # Visit children
            for child in node.children:
                visit(child, parent_name)

        visit(tree.root_node)
        return symbols

    def _extract_c_symbols(self, tree: Any, code: str) -> list[Symbol]:
        """Extract symbols from C code."""
        symbols: list[Symbol] = []

        def visit(node: Any, parent_name: str | None = None) -> None:
            """Recursively visit nodes."""
            if node.type == "function_definition":
                declarator = None
                for child in node.children:
                    if child.type == "function_declarator":
                        declarator = child
                        break

                if declarator:
                    name = None
                    for child in declarator.children:
                        if child.type == "identifier":
                            name = code[child.start_byte : child.end_byte]
                            break

                    if name:
                        full_name = f"{parent_name}.{name}" if parent_name else name
                        symbols.append(
                            Symbol(
                                name=name,
                                qualified_name=full_name,
                                type=SymbolType.FUNCTION,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                            )
                        )

            elif node.type == "struct_specifier":
                name = None
                for child in node.children:
                    if child.type == "type_identifier":
                        name = code[child.start_byte : child.end_byte]
                        break

                if name:
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=name,
                            type=SymbolType.CLASS,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                    )

            elif node.type == "enum_specifier":
                name = None
                for child in node.children:
                    if child.type == "type_identifier":
                        name = code[child.start_byte : child.end_byte]
                        break

                if name:
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=name,
                            type=SymbolType.CLASS,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                    )

            for child in node.children:
                visit(child, parent_name)

        visit(tree.root_node)
        return symbols

    def _extract_cpp_symbols(self, tree: Any, code: str) -> list[Symbol]:
        """Extract symbols from C++ code."""
        symbols: list[Symbol] = []

        def visit(node: Any, parent_name: str | None = None) -> None:
            """Recursively visit nodes."""
            if node.type == "function_definition":
                declarator = None
                for child in node.children:
                    if child.type in ("function_declarator", "qualified_identifier"):
                        declarator = child
                        break

                if declarator:
                    name = None
                    if declarator.type == "function_declarator":
                        for child in declarator.children:
                            if child.type in (
                                "identifier",
                                "field_identifier",
                                "qualified_identifier",
                            ):
                                name = code[child.start_byte : child.end_byte]
                                break
                    else:
                        name = code[declarator.start_byte : declarator.end_byte]

                    if name:
                        full_name = f"{parent_name}.{name}" if parent_name else name
                        is_method = parent_name is not None
                        symbol_type = SymbolType.METHOD if is_method else SymbolType.FUNCTION

                        symbols.append(
                            Symbol(
                                name=name.split("::")[-1] if "::" in name else name,
                                qualified_name=full_name,
                                type=symbol_type,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                            )
                        )

            elif node.type == "class_specifier":
                name = None
                for child in node.children:
                    if child.type == "type_identifier":
                        name = code[child.start_byte : child.end_byte]
                        break

                if name:
                    full_name = f"{parent_name}.{name}" if parent_name else name

                    bases: list[str] = []
                    for child in node.children:
                        if child.type == "base_class_clause":
                            for base_child in child.children:
                                if base_child.type == "type_identifier":
                                    bases.append(code[base_child.start_byte : base_child.end_byte])

                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=full_name,
                            type=SymbolType.CLASS,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            bases=bases,
                        )
                    )

                    for child in node.children:
                        if child.type == "field_declaration_list":
                            for method in child.children:
                                visit(method, name)
                    return

            elif node.type == "struct_specifier":
                name = None
                for child in node.children:
                    if child.type == "type_identifier":
                        name = code[child.start_byte : child.end_byte]
                        break

                if name:
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=name,
                            type=SymbolType.CLASS,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                    )

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
