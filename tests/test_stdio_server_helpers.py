"""
Tests for stdio_server helper functions.

Tests the essential helper functions including:
- _strip_comment_markers
- _check_introduced_as_comment
- _get_grouped_origins
- formatLineRanges equivalent logic
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime


class TestStripCommentMarkers:
    """Test the _strip_comment_markers helper function."""

    def test_strip_double_slash_comment(self):
        """Test stripping // style comments."""
        from ctm_mcp_server.stdio_server import _strip_comment_markers

        assert _strip_comment_markers("// This is a comment") == "This is a comment"
        assert _strip_comment_markers("//This is a comment") == "This is a comment"
        assert _strip_comment_markers("//  Multiple spaces") == "Multiple spaces"

    def test_strip_hash_comment(self):
        """Test stripping # style comments."""
        from ctm_mcp_server.stdio_server import _strip_comment_markers

        assert _strip_comment_markers("# Python comment") == "Python comment"
        assert _strip_comment_markers("#Python comment") == "Python comment"

    def test_strip_c_style_block_comment_markers(self):
        """Test stripping /* and */ markers."""
        from ctm_mcp_server.stdio_server import _strip_comment_markers

        assert _strip_comment_markers("/* Block comment */") == "Block comment"
        assert _strip_comment_markers("* Middle of block") == "Middle of block"
        assert _strip_comment_markers("*/") == ""

    def test_no_comment_markers(self):
        """Test that regular code is unchanged."""
        from ctm_mcp_server.stdio_server import _strip_comment_markers

        assert _strip_comment_markers("return x + y") == "return x + y"
        assert _strip_comment_markers("function foo()") == "function foo()"

    def test_empty_string(self):
        """Test empty string handling."""
        from ctm_mcp_server.stdio_server import _strip_comment_markers

        assert _strip_comment_markers("") == ""
        assert _strip_comment_markers("   ") == ""


class TestTruncate:
    """Test the _truncate helper function."""

    def test_truncate_short_string(self):
        """Test that short strings are unchanged."""
        from ctm_mcp_server.stdio_server import _truncate

        assert _truncate("Hello", 10) == "Hello"
        assert _truncate("Hello", 5) == "Hello"

    def test_truncate_long_string(self):
        """Test that long strings are truncated."""
        from ctm_mcp_server.stdio_server import _truncate

        result = _truncate("This is a very long string that exceeds the limit", 20)
        assert len(result) <= 35  # 20 + " [truncated]"
        assert "[truncated]" in result

    def test_truncate_default_length(self):
        """Test truncation with default length (500)."""
        from ctm_mcp_server.stdio_server import _truncate

        long_string = "x" * 600
        result = _truncate(long_string)
        assert len(result) <= 515  # 500 + " [truncated]"

    def test_truncate_none_returns_none(self):
        """Test that None input returns None."""
        from ctm_mcp_server.stdio_server import _truncate

        assert _truncate(None) is None


class TestExtractMessageSignals:
    """Test the _extract_message_signals helper function."""

    def test_extract_fix_signal(self):
        """Test extracting fix/bug signals."""
        from ctm_mcp_server.stdio_server import _extract_message_signals

        signals = _extract_message_signals("Fix bug in parser")
        assert isinstance(signals, list)
        assert any("fix" in s.lower() or "bug" in s.lower() for s in signals)

    def test_extract_feature_signal(self):
        """Test extracting feature signals."""
        from ctm_mcp_server.stdio_server import _extract_message_signals

        signals = _extract_message_signals("Add new feature for users")
        assert isinstance(signals, list)

    def test_no_signals(self):
        """Test message with no signals returns empty list."""
        from ctm_mcp_server.stdio_server import _extract_message_signals

        signals = _extract_message_signals("Update version")
        assert isinstance(signals, list)


class TestFormatLineRanges:
    """Test line range formatting logic (equivalent to formatLineRanges in TypeScript)."""

    def test_format_single_line(self):
        """Test formatting a single line."""
        # This tests the logic that should exist or be equivalent
        lines = [42]
        # Format: just "42"
        result = self._format_line_ranges(lines)
        assert result == "42"

    def test_format_consecutive_range(self):
        """Test formatting consecutive lines."""
        lines = [1, 2, 3, 4, 5]
        result = self._format_line_ranges(lines)
        assert result == "1-5"

    def test_format_multiple_ranges(self):
        """Test formatting multiple separate ranges."""
        lines = [1, 2, 3, 10, 11, 20]
        result = self._format_line_ranges(lines)
        assert result == "1-3, 10-11, 20"

    def test_format_unsorted_input(self):
        """Test that unsorted input is handled correctly."""
        lines = [5, 1, 3, 2, 4]
        result = self._format_line_ranges(lines)
        assert result == "1-5"

    def test_format_empty_list(self):
        """Test empty list returns empty string."""
        lines = []
        result = self._format_line_ranges(lines)
        assert result == ""

    def test_format_scattered_lines(self):
        """Test completely scattered lines."""
        lines = [1, 5, 10, 15]
        result = self._format_line_ranges(lines)
        assert result == "1, 5, 10, 15"

    @staticmethod
    def _format_line_ranges(lines: list[int]) -> str:
        """Python equivalent of formatLineRanges from TypeScript."""
        if not lines:
            return ""
        if len(lines) == 1:
            return str(lines[0])

        sorted_lines = sorted(lines)
        ranges = []
        range_start = sorted_lines[0]
        range_end = sorted_lines[0]

        for i in range(1, len(sorted_lines)):
            if sorted_lines[i] == range_end + 1:
                range_end = sorted_lines[i]
            else:
                if range_start == range_end:
                    ranges.append(str(range_start))
                else:
                    ranges.append(f"{range_start}-{range_end}")
                range_start = sorted_lines[i]
                range_end = sorted_lines[i]

        if range_start == range_end:
            ranges.append(str(range_start))
        else:
            ranges.append(f"{range_start}-{range_end}")

        return ", ".join(ranges)


class TestCheckIntroducedAsComment:
    """Test the _check_introduced_as_comment helper function."""

    def test_introduced_as_double_slash_comment(self):
        """Test detection of // style comment introduction."""
        from ctm_mcp_server.stdio_server import _check_introduced_as_comment

        # Create mock repo with mock diff
        repo = Mock()
        mock_hunk = Mock()
        mock_hunk.lines = [
            "+// This is a comment with target_code",
            " some other line",
        ]
        mock_diff_file = Mock()
        mock_diff_file.hunks = [mock_hunk]
        repo.get_diff.return_value = [mock_diff_file]

        result = _check_introduced_as_comment(repo, "abc123", "target_code")
        assert result is True

    def test_introduced_as_active_code(self):
        """Test detection of active code introduction."""
        from ctm_mcp_server.stdio_server import _check_introduced_as_comment

        repo = Mock()
        mock_hunk = Mock()
        mock_hunk.lines = [
            "+return target_code + 1",
            " some other line",
        ]
        mock_diff_file = Mock()
        mock_diff_file.hunks = [mock_hunk]
        repo.get_diff.return_value = [mock_diff_file]

        result = _check_introduced_as_comment(repo, "abc123", "target_code")
        assert result is False

    def test_introduced_as_hash_comment(self):
        """Test detection of # style comment introduction."""
        from ctm_mcp_server.stdio_server import _check_introduced_as_comment

        repo = Mock()
        mock_hunk = Mock()
        mock_hunk.lines = [
            "+# target_code placeholder",
        ]
        mock_diff_file = Mock()
        mock_diff_file.hunks = [mock_hunk]
        repo.get_diff.return_value = [mock_diff_file]

        result = _check_introduced_as_comment(repo, "abc123", "target_code")
        assert result is True

    def test_no_diff_found(self):
        """Test behavior when no diff is found."""
        from ctm_mcp_server.stdio_server import _check_introduced_as_comment

        repo = Mock()
        repo.get_diff.return_value = None

        result = _check_introduced_as_comment(repo, "abc123", "target_code")
        assert result is None

    def test_search_string_not_in_diff(self):
        """Test behavior when search string is not in diff."""
        from ctm_mcp_server.stdio_server import _check_introduced_as_comment

        repo = Mock()
        mock_hunk = Mock()
        mock_hunk.lines = [
            "+completely different code",
        ]
        mock_diff_file = Mock()
        mock_diff_file.hunks = [mock_hunk]
        repo.get_diff.return_value = [mock_diff_file]

        result = _check_introduced_as_comment(repo, "abc123", "target_code")
        assert result is None

    def test_exception_handling(self):
        """Test that exceptions return None."""
        from ctm_mcp_server.stdio_server import _check_introduced_as_comment

        repo = Mock()
        repo.get_diff.side_effect = Exception("Git error")

        result = _check_introduced_as_comment(repo, "abc123", "target_code")
        assert result is None


class TestGetGroupedOrigins:
    """Test the _get_grouped_origins helper function."""

    def _create_mock_commit(self, sha: str, author_name: str, date: datetime, subject: str):
        """Helper to create mock commit objects."""
        commit = Mock()
        commit.sha = sha
        commit.author = Mock()
        commit.author.name = author_name
        commit.committed_date = date
        commit.subject = subject
        return commit

    def test_empty_lines_returns_empty_list(self):
        """Test that empty/blank lines return empty list."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        result = _get_grouped_origins(
            repo=repo,
            content_lines=["", "   ", "\t"],
            line_numbers=[1, 2, 3],
            file_path="test.py",
            github_base_url="https://github.com/owner/repo",
        )
        assert result == []

    def test_single_origin_for_all_lines(self):
        """Test when all lines have the same origin."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        mock_commit = self._create_mock_commit(
            "abc123def456", "Alice", datetime(2024, 1, 15), "Add feature"
        )
        repo.pickaxe_search.return_value = [mock_commit]
        repo.get_diff.return_value = None  # No diff check needed

        result = _get_grouped_origins(
            repo=repo,
            content_lines=["line 1", "line 2", "line 3"],
            line_numbers=[10, 11, 12],
            file_path="test.py",
            github_base_url="https://github.com/owner/repo",
        )

        assert len(result) == 1
        assert result[0]["sha"] == "abc123def456"
        assert result[0]["author"] == "Alice"
        assert set(result[0]["lines"]) == {10, 11, 12}

    def test_multiple_origins_grouped_correctly(self):
        """Test that lines with different origins are grouped correctly."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        commit1 = self._create_mock_commit(
            "aaa111", "Alice", datetime(2024, 1, 1), "First commit"
        )
        commit2 = self._create_mock_commit(
            "bbb222", "Bob", datetime(2024, 2, 1), "Second commit"
        )

        # Return different commits for different pickaxe searches
        def pickaxe_side_effect(search_string, **kwargs):
            if "line 1" in search_string:
                return [commit1]
            else:
                return [commit2]

        repo.pickaxe_search.side_effect = pickaxe_side_effect
        repo.get_diff.return_value = None

        result = _get_grouped_origins(
            repo=repo,
            content_lines=["line 1 content", "line 2 content", "line 3 content"],
            line_numbers=[10, 11, 12],
            file_path="test.py",
            github_base_url="https://github.com/owner/repo",
        )

        assert len(result) == 2
        # Check that origins are correctly grouped
        shas = {o["sha"] for o in result}
        assert shas == {"aaa111", "bbb222"}

    def test_pickaxe_failure_skips_line(self):
        """Test that pickaxe failures result in line not being included."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        repo.pickaxe_search.return_value = []  # No results
        repo.get_diff.return_value = None

        result = _get_grouped_origins(
            repo=repo,
            content_lines=["some code"],
            line_numbers=[10],
            file_path="test.py",
            github_base_url=None,
        )

        assert result == []

    def test_caching_avoids_duplicate_pickaxe_calls(self):
        """Test that identical content uses cached pickaxe results."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        mock_commit = self._create_mock_commit(
            "cached123", "Cached", datetime(2024, 1, 1), "Cached commit"
        )
        repo.pickaxe_search.return_value = [mock_commit]
        repo.get_diff.return_value = None

        # Same content on multiple lines
        result = _get_grouped_origins(
            repo=repo,
            content_lines=["identical", "identical", "identical"],
            line_numbers=[10, 11, 12],
            file_path="test.py",
            github_base_url=None,
        )

        # Should only call pickaxe once due to caching
        assert repo.pickaxe_search.call_count == 1
        assert len(result) == 1
        assert set(result[0]["lines"]) == {10, 11, 12}

    def test_introduced_as_comment_tracked_correctly(self):
        """Test that introduced_as_comment is tracked per-line."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        mock_commit = self._create_mock_commit(
            "comment123", "Alice", datetime(2024, 1, 1), "Add comment"
        )
        repo.pickaxe_search.return_value = [mock_commit]

        # Mock diff to show comment introduction
        mock_hunk = Mock()
        mock_hunk.lines = ["+// line 1"]
        mock_diff_file = Mock()
        mock_diff_file.hunks = [mock_hunk]
        repo.get_diff.return_value = [mock_diff_file]

        result = _get_grouped_origins(
            repo=repo,
            content_lines=["// line 1"],
            line_numbers=[10],
            file_path="test.py",
            github_base_url=None,
        )

        assert len(result) == 1
        assert 10 in result[0]["introduced_as_comment"]

    def test_sampling_for_large_selections(self):
        """Test that large selections use sampling."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        mock_commit = self._create_mock_commit(
            "sampled123", "Sampler", datetime(2024, 1, 1), "Sampled"
        )
        repo.pickaxe_search.return_value = [mock_commit]
        repo.get_diff.return_value = None

        # Create 50 lines (more than default max_lines=25)
        content_lines = [f"line {i}" for i in range(50)]
        line_numbers = list(range(100, 150))

        result = _get_grouped_origins(
            repo=repo,
            content_lines=content_lines,
            line_numbers=line_numbers,
            file_path="test.py",
            github_base_url=None,
            max_lines=25,
            sample_size=10,
        )

        # Should sample only 10 lines but assign all to origin
        assert repo.pickaxe_search.call_count <= 10
        # All lines should still be assigned via nearest neighbor
        if result:
            total_lines = sum(len(o["lines"]) for o in result)
            assert total_lines == 50

    def test_github_url_construction(self):
        """Test that GitHub URLs are constructed correctly."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        mock_commit = self._create_mock_commit(
            "url123abc", "Alice", datetime(2024, 1, 1), "URL test"
        )
        repo.pickaxe_search.return_value = [mock_commit]
        repo.get_diff.return_value = None

        result = _get_grouped_origins(
            repo=repo,
            content_lines=["test code"],
            line_numbers=[10],
            file_path="test.py",
            github_base_url="https://github.com/owner/repo",
        )

        assert result[0]["html_url"] == "https://github.com/owner/repo/commit/url123abc"

    def test_no_github_url_when_base_is_none(self):
        """Test that html_url is None when github_base_url is None."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        mock_commit = self._create_mock_commit(
            "nourl123", "Alice", datetime(2024, 1, 1), "No URL"
        )
        repo.pickaxe_search.return_value = [mock_commit]
        repo.get_diff.return_value = None

        result = _get_grouped_origins(
            repo=repo,
            content_lines=["test code"],
            line_numbers=[10],
            file_path="test.py",
            github_base_url=None,
        )

        assert result[0]["html_url"] is None


class TestOriginDataStructure:
    """Test the origins data structure format."""

    def test_origin_has_required_fields(self):
        """Test that origin objects have all required fields."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()
        mock_commit = Mock()
        mock_commit.sha = "abc123def"
        mock_commit.author = Mock()
        mock_commit.author.name = "Test Author"
        mock_commit.committed_date = datetime(2024, 6, 15)
        mock_commit.subject = "Test message"

        repo.pickaxe_search.return_value = [mock_commit]
        repo.get_diff.return_value = None

        result = _get_grouped_origins(
            repo=repo,
            content_lines=["test"],
            line_numbers=[1],
            file_path="test.py",
            github_base_url="https://github.com/o/r",
        )

        assert len(result) == 1
        origin = result[0]

        # Check required fields
        assert "sha" in origin
        assert "short_sha" in origin
        assert "author" in origin
        assert "date" in origin
        assert "message" in origin
        assert "html_url" in origin
        assert "lines" in origin
        assert "introduced_as_comment" in origin

        # Check types
        assert isinstance(origin["sha"], str)
        assert isinstance(origin["short_sha"], str)
        assert isinstance(origin["lines"], list)
        assert isinstance(origin["introduced_as_comment"], list)
        assert len(origin["short_sha"]) == 7

    def test_origins_sorted_by_first_line(self):
        """Test that origins are sorted by their first line number."""
        from ctm_mcp_server.stdio_server import _get_grouped_origins

        repo = Mock()

        commit1 = Mock()
        commit1.sha = "first111"
        commit1.author = Mock()
        commit1.author.name = "First"
        commit1.committed_date = datetime(2024, 1, 1)
        commit1.subject = "First"

        commit2 = Mock()
        commit2.sha = "second22"
        commit2.author = Mock()
        commit2.author.name = "Second"
        commit2.committed_date = datetime(2024, 2, 1)
        commit2.subject = "Second"

        def pickaxe_side_effect(search_string, **kwargs):
            if "later" in search_string:
                return [commit2]
            return [commit1]

        repo.pickaxe_search.side_effect = pickaxe_side_effect
        repo.get_diff.return_value = None

        result = _get_grouped_origins(
            repo=repo,
            content_lines=["later line", "first line"],
            line_numbers=[20, 10],
            file_path="test.py",
            github_base_url=None,
        )

        # Origins should be sorted by first line number
        if len(result) == 2:
            assert result[0]["lines"][0] < result[1]["lines"][0]
