"""
Tests for the multi-language code parser.

Tests symbol extraction for Python, JavaScript, TypeScript, Go, and Rust.
"""

import pytest

from ctm_mcp_server.parsing.parser import CodeParser, ParserError
from ctm_mcp_server.models.symbol_models import SymbolType


class TestLanguageDetection:
    """Test language detection from file extensions."""

    def test_python_extensions(self):
        """Test Python file extension detection."""
        parser = CodeParser()
        assert parser.detect_language("test.py") == "python"
        assert parser.detect_language("test.pyi") == "python"

    def test_javascript_extensions(self):
        """Test JavaScript file extension detection."""
        parser = CodeParser()
        assert parser.detect_language("test.js") == "javascript"
        assert parser.detect_language("test.jsx") == "javascript"
        assert parser.detect_language("test.mjs") == "javascript"
        assert parser.detect_language("test.cjs") == "javascript"

    def test_typescript_extensions(self):
        """Test TypeScript file extension detection."""
        parser = CodeParser()
        assert parser.detect_language("test.ts") == "typescript"
        assert parser.detect_language("test.tsx") == "typescript"

    def test_go_extensions(self):
        """Test Go file extension detection."""
        parser = CodeParser()
        assert parser.detect_language("test.go") == "go"

    def test_rust_extensions(self):
        """Test Rust file extension detection."""
        parser = CodeParser()
        assert parser.detect_language("test.rs") == "rust"

    def test_c_extensions(self):
        """Test C file extension detection."""
        parser = CodeParser()
        assert parser.detect_language("test.c") == "c"
        assert parser.detect_language("test.h") == "c"

    def test_cpp_extensions(self):
        """Test C++ file extension detection."""
        parser = CodeParser()
        assert parser.detect_language("test.cpp") == "cpp"
        assert parser.detect_language("test.cc") == "cpp"
        assert parser.detect_language("test.hpp") == "cpp"
        assert parser.detect_language("test.hxx") == "cpp"

    def test_unsupported_extension(self):
        """Test unsupported file extension returns None."""
        parser = CodeParser()
        assert parser.detect_language("test.java") is None
        assert parser.detect_language("test.php") is None
        assert parser.detect_language("test.rb") is None


class TestPythonSymbolExtraction:
    """Test Python symbol extraction."""

    def test_extract_function(self):
        """Test extracting a simple function."""
        code = """
def hello():
    return "Hello, World!"
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "python")

        assert len(symbols) == 1
        assert symbols[0].name == "hello"
        assert symbols[0].type == SymbolType.FUNCTION
        assert symbols[0].start_line == 2

    def test_extract_class(self):
        """Test extracting a class with methods."""
        code = """
class Calculator:
    def add(self, x, y):
        return x + y

    def subtract(self, x, y):
        return x - y
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "python")

        assert len(symbols) == 3

        # Check class
        class_sym = [s for s in symbols if s.type == SymbolType.CLASS][0]
        assert class_sym.name == "Calculator"
        assert class_sym.start_line == 2

        # Check methods
        methods = [s for s in symbols if s.type == SymbolType.METHOD]
        assert len(methods) == 2
        assert methods[0].qualified_name == "Calculator.add"
        assert methods[1].qualified_name == "Calculator.subtract"


class TestJavaScriptSymbolExtraction:
    """Test JavaScript symbol extraction."""

    def test_extract_function_declaration(self):
        """Test extracting function declarations."""
        code = """
function multiply(a, b) {
    return a * b;
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "javascript")

        assert len(symbols) == 1
        assert symbols[0].name == "multiply"
        assert symbols[0].type == SymbolType.FUNCTION
        assert symbols[0].start_line == 2

    def test_extract_arrow_function(self):
        """Test extracting arrow functions."""
        code = """
const divide = (a, b) => {
    return a / b;
};
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "javascript")

        assert len(symbols) == 1
        assert symbols[0].name == "divide"
        assert symbols[0].type == SymbolType.FUNCTION
        assert symbols[0].start_line == 2

    def test_extract_class_with_methods(self):
        """Test extracting ES6 class with methods."""
        code = """
class Calculator {
    constructor() {
        this.value = 0;
    }

    add(x) {
        this.value += x;
        return this;
    }

    subtract(x) {
        this.value -= x;
        return this;
    }
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "javascript")

        # Should have: 1 class + 3 methods (constructor, add, subtract)
        assert len(symbols) == 4

        # Check class
        class_sym = [s for s in symbols if s.type == SymbolType.CLASS][0]
        assert class_sym.name == "Calculator"
        assert class_sym.start_line == 2

        # Check methods
        methods = [s for s in symbols if s.type == SymbolType.METHOD]
        assert len(methods) == 3
        method_names = {m.name for m in methods}
        assert method_names == {"constructor", "add", "subtract"}

    def test_extract_mixed_functions(self):
        """Test extracting mixed function types."""
        code = """
class MyClass {
    method1() {
        return 1;
    }
}

function regularFunc() {
    return 2;
}

const arrowFunc = () => {
    return 3;
};
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "javascript")

        assert len(symbols) == 4

        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        methods = [s for s in symbols if s.type == SymbolType.METHOD]
        functions = [s for s in symbols if s.type == SymbolType.FUNCTION]

        assert len(classes) == 1
        assert len(methods) == 1
        assert len(functions) == 2


class TestTypeScriptSymbolExtraction:
    """Test TypeScript symbol extraction."""

    def test_extract_typed_function(self):
        """Test extracting TypeScript function with types."""
        code = """
function add(x: number, y: number): number {
    return x + y;
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "typescript")

        assert len(symbols) == 1
        assert symbols[0].name == "add"
        assert symbols[0].type == SymbolType.FUNCTION

    def test_extract_interface_and_class(self):
        """Test extracting TypeScript class implementing interface."""
        code = """
interface User {
    id: number;
    name: string;
}

class UserService {
    private users: User[] = [];

    addUser(user: User): void {
        this.users.push(user);
    }

    getUser(id: number): User | undefined {
        return this.users.find(u => u.id === id);
    }
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "typescript")

        # Should have: 1 class + 2 methods (addUser, getUser)
        # Note: interfaces are not extracted as they're not in our node types
        # The arrow function inside getUser might be extracted
        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        methods = [s for s in symbols if s.type == SymbolType.METHOD]

        assert len(classes) == 1
        assert classes[0].name == "UserService"
        assert len(methods) >= 2  # At least addUser and getUser


class TestGoSymbolExtraction:
    """Test Go symbol extraction."""

    def test_extract_function(self):
        """Test extracting Go function."""
        code = """
package main

func Add(x int, y int) int {
    return x + y
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "go")

        assert len(symbols) == 1
        assert symbols[0].name == "Add"
        assert symbols[0].type == SymbolType.FUNCTION
        assert symbols[0].start_line == 4

    def test_extract_struct_and_method(self):
        """Test extracting Go struct and method."""
        code = """
package main

type Calculator struct {
    value int
}

func (c *Calculator) Add(x int) {
    c.value += x
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "go")

        # Should have: 1 struct (as CLASS) + 1 method
        assert len(symbols) == 2

        structs = [s for s in symbols if s.type == SymbolType.CLASS]
        methods = [s for s in symbols if s.type == SymbolType.METHOD]

        assert len(structs) == 1
        assert structs[0].name == "Calculator"

        assert len(methods) == 1
        assert methods[0].name == "Add"


class TestRustSymbolExtraction:
    """Test Rust symbol extraction."""

    def test_extract_function(self):
        """Test extracting Rust function."""
        code = """
fn add(x: i32, y: i32) -> i32 {
    x + y
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "rust")

        assert len(symbols) == 1
        assert symbols[0].name == "add"
        assert symbols[0].type == SymbolType.FUNCTION
        assert symbols[0].start_line == 2

    def test_extract_struct_and_impl(self):
        """Test extracting Rust struct and impl block."""
        code = """
struct Calculator {
    value: i32,
}

impl Calculator {
    fn new() -> Self {
        Calculator { value: 0 }
    }

    fn add(&mut self, x: i32) {
        self.value += x;
    }
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "rust")

        # Should have: 1 struct (as CLASS) + 2 methods (new, add)
        assert len(symbols) == 3

        structs = [s for s in symbols if s.type == SymbolType.CLASS]
        methods = [s for s in symbols if s.type == SymbolType.METHOD]

        assert len(structs) == 1
        assert structs[0].name == "Calculator"

        assert len(methods) == 2
        method_names = {m.name for m in methods}
        assert method_names == {"new", "add"}

    def test_extract_enum(self):
        """Test extracting Rust enum."""
        code = """
enum Color {
    Red,
    Green,
    Blue,
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "rust")

        assert len(symbols) == 1
        assert symbols[0].name == "Color"
        assert symbols[0].type == SymbolType.CLASS  # Enums are treated as CLASS


class TestParserErrors:
    """Test parser error handling."""

    def test_unsupported_language(self):
        """Test that unsupported language raises error."""
        parser = CodeParser()
        with pytest.raises(ParserError, match="Unsupported language"):
            parser.parse("code", "cobol")

    def test_symbol_extraction_unsupported_language(self):
        """Test that symbol extraction for unsupported language raises error."""
        parser = CodeParser()
        with pytest.raises(ParserError, match="Unsupported language"):
            parser.extract_symbols("code", "cobol")


class TestComplexScenarios:
    """Test complex, real-world scenarios."""

    def test_nested_javascript_classes(self):
        """Test extracting nested patterns in JavaScript."""
        code = """
class Outer {
    constructor() {
        this.inner = class Inner {
            method() {
                return 42;
            }
        };
    }

    outerMethod() {
        return this.inner;
    }
}

const helper = (x) => x * 2;
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "javascript")

        # Should extract: Outer class, Inner class, constructor, method, outerMethod, helper
        assert len(symbols) >= 4  # At least the main symbols

        class_names = {s.name for s in symbols if s.type == SymbolType.CLASS}
        assert "Outer" in class_names

    def test_typescript_generic_class(self):
        """Test TypeScript class with generics."""
        code = """
class Container<T> {
    private value: T;

    constructor(value: T) {
        this.value = value;
    }

    getValue(): T {
        return this.value;
    }
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "typescript")

        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        methods = [s for s in symbols if s.type == SymbolType.METHOD]

        assert len(classes) == 1
        assert classes[0].name == "Container"
        assert len(methods) >= 2  # constructor and getValue

    def test_go_interface_and_implementation(self):
        """Test Go interface and implementation."""
        code = """
package main

type Reader interface {
    Read() string
}

type FileReader struct {
    path string
}

func (f *FileReader) Read() string {
    return f.path
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "go")

        # Should have: Reader (interface as CLASS), FileReader (struct as CLASS), Read method
        # Note: interfaces might not be extracted depending on implementation
        structs = [s for s in symbols if s.type == SymbolType.CLASS]
        methods = [s for s in symbols if s.type == SymbolType.METHOD]

        assert len(structs) >= 1  # At least FileReader
        assert len(methods) == 1
        assert methods[0].name == "Read"

    def test_rust_trait_and_implementation(self):
        """Test Rust trait and implementation."""
        code = """
trait Drawable {
    fn draw(&self);
}

struct Circle {
    radius: f64,
}

impl Drawable for Circle {
    fn draw(&self) {
        println!("Drawing circle");
    }
}
"""
        parser = CodeParser()
        symbols = parser.extract_symbols(code, "rust")

        # Should have: Drawable (trait as CLASS), Circle (struct as CLASS), draw method
        structs = [s for s in symbols if s.type == SymbolType.CLASS]
        methods = [s for s in symbols if s.type == SymbolType.METHOD]

        assert len(structs) == 2  # Drawable and Circle
        assert len(methods) == 1
        assert methods[0].name == "draw"
