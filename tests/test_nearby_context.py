"""
Tests for nearby_context functionality.

Verifies that nearby_context is sent for ALL code types (not just commented code)
when include_nearby_context=True.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path
import tempfile


class TestGetNearbyContext:
    """Test the _get_nearby_context helper function."""

    def test_get_nearby_context_middle_of_file(self, temp_dir):
        """Test getting nearby context for lines in the middle of a file."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        # Create actual file in temp directory
        test_file = temp_dir / "test.py"
        test_file.write_text("\n".join([f"line {i}" for i in range(1, 31)]))

        # Create mock repo with path attribute
        mock_repo = Mock()
        mock_repo.path = temp_dir

        result = _get_nearby_context(
            repo=mock_repo,
            file_path="test.py",
            line_start=15,
            line_end=16,
            context_lines=5,
        )

        # Should have both before and after context
        assert result.get("before") is not None
        assert result.get("after") is not None
        assert result["before"]["content"] is not None
        assert result["after"]["content"] is not None
        # Before should contain lines before selection
        assert "line 10" in result["before"]["content"]
        # After should contain lines after selection
        assert "line 17" in result["after"]["content"]

    def test_get_nearby_context_start_of_file(self, temp_dir):
        """Test getting nearby context for lines at the start of a file."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        test_file = temp_dir / "test.py"
        test_file.write_text("\n".join([f"line {i}" for i in range(1, 31)]))

        mock_repo = Mock()
        mock_repo.path = temp_dir

        result = _get_nearby_context(
            repo=mock_repo,
            file_path="test.py",
            line_start=1,
            line_end=2,
            context_lines=5,
        )

        # Before should be empty/None at start of file
        assert result["before"]["content"] is None or result["before"]["content"] == ""
        # After should still have content
        assert result["after"]["content"] is not None
        assert "line 3" in result["after"]["content"]

    def test_get_nearby_context_end_of_file(self, temp_dir):
        """Test getting nearby context for lines at the end of a file."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        test_file = temp_dir / "test.py"
        test_file.write_text("\n".join([f"line {i}" for i in range(1, 31)]))

        mock_repo = Mock()
        mock_repo.path = temp_dir

        result = _get_nearby_context(
            repo=mock_repo,
            file_path="test.py",
            line_start=29,
            line_end=30,
            context_lines=5,
        )

        # Before should have content
        assert result["before"]["content"] is not None
        assert "line 24" in result["before"]["content"]
        # After should be empty/None at end of file
        assert result["after"]["content"] is None or result["after"]["content"] == ""

    def test_get_nearby_context_empty_file(self, temp_dir):
        """Test handling of empty file."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        test_file = temp_dir / "empty.py"
        test_file.write_text("")

        mock_repo = Mock()
        mock_repo.path = temp_dir

        result = _get_nearby_context(
            repo=mock_repo,
            file_path="empty.py",
            line_start=1,
            line_end=1,
            context_lines=5,
        )

        # Should return empty dict for empty file
        assert result == {}

    def test_get_nearby_context_file_not_found(self, temp_dir):
        """Test handling when file doesn't exist."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        mock_repo = Mock()
        mock_repo.path = temp_dir

        result = _get_nearby_context(
            repo=mock_repo,
            file_path="nonexistent.py",
            line_start=1,
            line_end=1,
            context_lines=5,
        )

        # Should return empty dict
        assert result == {}

    def test_get_nearby_context_exception_handling(self, temp_dir):
        """Test that exceptions are handled gracefully."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        mock_repo = Mock()
        # Make path property raise an exception
        type(mock_repo).path = property(lambda self: (_ for _ in ()).throw(Exception("error")))

        result = _get_nearby_context(
            repo=mock_repo,
            file_path="error.py",
            line_start=1,
            line_end=1,
            context_lines=5,
        )

        # Should return empty dict on exception
        assert result == {}

    def test_get_nearby_context_default_context_lines(self, temp_dir):
        """Test that default context_lines is 10."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        test_file = temp_dir / "test.py"
        test_file.write_text("\n".join([f"line {i}" for i in range(1, 51)]))

        mock_repo = Mock()
        mock_repo.path = temp_dir

        result = _get_nearby_context(
            repo=mock_repo,
            file_path="test.py",
            line_start=25,
            line_end=26,
        )

        # Default is 10 lines, so before should have lines 15-24
        assert result["before"]["content"] is not None
        before_lines = result["before"]["content"].split("\n")
        assert len(before_lines) == 10

        # After should have lines 27-36
        assert result["after"]["content"] is not None
        after_lines = result["after"]["content"].split("\n")
        assert len(after_lines) == 10


class TestNearbyContextForAllCodeTypes:
    """Test that nearby_context is sent for ALL code types, not just commented code."""

    def test_nearby_context_for_regular_code(self, temp_dir):
        """Test that regular (non-commented) code gets nearby_context."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        file_content = """import os
import sys

def hello():
    print("Hello World")

def goodbye():
    print("Goodbye World")

if __name__ == "__main__":
    hello()
    goodbye()
"""
        test_file = temp_dir / "main.py"
        test_file.write_text(file_content)

        mock_repo = Mock()
        mock_repo.path = temp_dir

        # Get context for the hello() function (lines 4-5)
        result = _get_nearby_context(
            repo=mock_repo,
            file_path="main.py",
            line_start=4,
            line_end=5,
            context_lines=3,
        )

        # Should have both before and after context
        assert result.get("before") is not None
        assert result.get("after") is not None
        # Before should contain imports
        assert "import" in result["before"]["content"]
        # After should contain goodbye function
        assert "goodbye" in result["after"]["content"]

    def test_nearby_context_for_commented_code(self, temp_dir):
        """Test that commented code also gets nearby_context."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        file_content = """def process():
    # Step 1: Initialize
    data = []

    # Old implementation (commented out):
    # for i in range(10):
    #     data.append(i * 2)

    # New implementation:
    data = [i * 2 for i in range(10)]

    return data
"""
        test_file = temp_dir / "process.py"
        test_file.write_text(file_content)

        mock_repo = Mock()
        mock_repo.path = temp_dir

        # Get context for commented lines (lines 6-7)
        result = _get_nearby_context(
            repo=mock_repo,
            file_path="process.py",
            line_start=6,
            line_end=7,
            context_lines=3,
        )

        # Should have both before and after context
        assert result.get("before") is not None
        assert result.get("after") is not None
        # Before should show context
        assert result["before"]["content"] is not None
        # After should contain the new implementation
        assert result["after"]["content"] is not None

    def test_nearby_context_for_pybind11_code(self, temp_dir):
        """Test nearby_context for pybind11 bindings (real-world use case)."""
        from ctm_mcp_server.stdio_server import _get_nearby_context

        file_content = '''m.def("InitParams", []() {
    return std::make_shared<CCParams<CryptoContextBFVRNS>>();
});

// Commented binding:
// m.def("SetParams", [](CCParams<CryptoContextBFVRNS>& params) {
//     params.SetPlaintextModulus(65537);
// });

m.def("GetParams", [](CCParams<CryptoContextBFVRNS>& params) {
    return params.GetPlaintextModulus();
});
'''
        test_file = temp_dir / "bindings.cpp"
        test_file.write_text(file_content)

        mock_repo = Mock()
        mock_repo.path = temp_dir

        # Get context for commented binding (lines 5-8)
        result = _get_nearby_context(
            repo=mock_repo,
            file_path="bindings.cpp",
            line_start=5,
            line_end=8,
            context_lines=3,
        )

        # Should have context showing active bindings before and after
        assert result.get("before") is not None
        assert result.get("after") is not None


class TestIncludeNearbyContextParameter:
    """Test that include_nearby_context parameter controls whether context is returned."""

    @pytest.mark.asyncio
    async def test_nearby_context_included_when_enabled(self, sample_repo):
        """Test that nearby_context is in result when include_nearby_context=True."""
        from ctm_mcp_server.stdio_server import _get_local_line_context

        # sample_repo fixture creates a repo with main.py
        result = await _get_local_line_context(
            repo_path=str(sample_repo),
            file_path="main.py",
            line_start=4,
            line_end=5,
            history_depth=1,
            include_discussions=False,
            include_nearby_context=True,  # Explicitly enabled
        )

        # Should have nearby_context in result
        assert "nearby_context" in result
        nearby = result["nearby_context"]
        # Should have before and/or after
        assert "before" in nearby or "after" in nearby

    @pytest.mark.asyncio
    async def test_nearby_context_excluded_when_disabled(self, sample_repo):
        """Test that nearby_context is NOT in result when include_nearby_context=False."""
        from ctm_mcp_server.stdio_server import _get_local_line_context

        result = await _get_local_line_context(
            repo_path=str(sample_repo),
            file_path="main.py",
            line_start=4,
            line_end=5,
            history_depth=1,
            include_discussions=False,
            include_nearby_context=False,  # Explicitly disabled
        )

        # Should NOT have nearby_context in result
        assert "nearby_context" not in result

    @pytest.mark.asyncio
    async def test_nearby_context_enabled_by_default(self, sample_repo):
        """Test that nearby_context is included by default (default=True)."""
        from ctm_mcp_server.stdio_server import _get_local_line_context

        result = await _get_local_line_context(
            repo_path=str(sample_repo),
            file_path="main.py",
            line_start=4,
            line_end=5,
            history_depth=1,
            include_discussions=False,
            # include_nearby_context not specified - should default to True
        )

        # Should have nearby_context by default
        assert "nearby_context" in result


class TestNearbyContextNotConditionalOnCommentedCode:
    """
    Critical test: Verify that nearby_context is NOT conditionally added
    based on whether the selected code is commented.

    This is the main assertion requested by the user.
    """

    @pytest.mark.asyncio
    async def test_nearby_context_for_non_commented_code(self, sample_repo):
        """
        Test that nearby_context is returned for regular (non-commented) code.
        This verifies the fix: nearby_context should be sent for ALL code.
        """
        from ctm_mcp_server.stdio_server import _get_local_line_context

        # main.py in sample_repo contains regular Python code (no comments)
        result = await _get_local_line_context(
            repo_path=str(sample_repo),
            file_path="main.py",
            line_start=4,  # The hello function line
            line_end=5,
            history_depth=1,
            include_discussions=False,
            include_nearby_context=True,
        )

        # Key assertion: nearby_context must be present for regular code
        assert "nearby_context" in result, (
            "nearby_context should be included for non-commented code! "
            "This is NOT conditional on whether code is commented."
        )

    @pytest.mark.asyncio
    async def test_pattern_detection_uses_nearby_context_for_commented_code(
        self, sample_repo
    ):
        """
        Test that pattern detection (like 'commented_with_active_alternative')
        uses nearby_context when code IS commented, but this doesn't affect
        whether nearby_context is included in the result.
        """
        from ctm_mcp_server.stdio_server import (
            _get_local_line_context,
            _detect_patterns,
        )

        # Create a file with commented code
        (sample_repo / "commented.py").write_text(
            """def active_function():
    return 42

# def commented_function():
#     return 0

def another_active():
    return 100
"""
        )

        # Commit the file
        import subprocess

        subprocess.run(["git", "add", "."], cwd=sample_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file with commented code"],
            cwd=sample_repo,
            check=True,
        )

        result = await _get_local_line_context(
            repo_path=str(sample_repo),
            file_path="commented.py",
            line_start=4,  # The commented function
            line_end=5,
            history_depth=1,
            include_discussions=False,
            include_nearby_context=True,
        )

        # nearby_context should be present
        assert "nearby_context" in result

        # Pattern detection may use this context, but that's separate
        # The key point: nearby_context is in result regardless of patterns
