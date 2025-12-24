import * as assert from 'assert';

/**
 * Test suite for line number calculation edge cases.
 *
 * VS Code's selection API is 0-indexed. When you select full lines by clicking
 * in the gutter or dragging, the selection.end cursor lands at column 0 of the
 * line AFTER your selection. This test suite verifies we handle this correctly.
 */

interface MockSelection {
    start: { line: number; character: number };
    end: { line: number; character: number };
}

/**
 * Calculate line numbers from VS Code selection (mimics extension.ts logic)
 */
function calculateLineNumbers(selection: MockSelection): { startLine: number; endLine: number } {
    // Calculate line numbers (1-indexed)
    // VS Code's selection is 0-indexed
    const startLine = selection.start.line + 1;

    // If selection ends at the beginning of a line (column 0), don't include that line
    // This happens when you select full lines - the cursor ends at the start of the next line
    let endLine = selection.end.line + 1;
    if (selection.end.character === 0 && selection.end.line > selection.start.line) {
        endLine = selection.end.line; // Don't add 1, use the previous line
    }

    return { startLine, endLine };
}

describe('Line Number Calculation Tests', () => {

    it('Single line selection (partial)', () => {
        // Select part of line 141 (0-indexed: line 140, char 4 to 20)
        const selection: MockSelection = {
            start: { line: 140, character: 4 },
            end: { line: 140, character: 20 }
        };

        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 141);
        assert.strictEqual(result.endLine, 141);
    });

    it('Full line selection (clicking in gutter) - lines 141-143', () => {
        // When selecting full lines 141-143 by clicking in gutter,
        // VS Code sets selection to:
        // - start: line 140 (0-indexed), char 0
        // - end: line 143 (0-indexed), char 0 (start of line 144!)
        const selection: MockSelection = {
            start: { line: 140, character: 0 },
            end: { line: 143, character: 0 }  // This is line 144 in 1-indexed!
        };

        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 141);
        assert.strictEqual(result.endLine, 143); // Should NOT be 144!
    });

    it('Dragging selection across multiple lines - lines 141-143', () => {
        // When dragging to select lines 141-143, ending at start of line 144
        const selection: MockSelection = {
            start: { line: 140, character: 8 },  // Starting mid-line 141
            end: { line: 143, character: 0 }      // Ending at start of line 144
        };

        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 141);
        assert.strictEqual(result.endLine, 143);
    });

    it('Selection ending mid-line (not at column 0)', () => {
        // Select lines 141-143, ending partway through line 143
        const selection: MockSelection = {
            start: { line: 140, character: 0 },
            end: { line: 142, character: 25 }  // Mid-way through line 143 (0-indexed)
        };

        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 141);
        assert.strictEqual(result.endLine, 143); // Should include line 143
    });

    it('Single full line selection - line 141 only', () => {
        // Select just line 141 by clicking in gutter
        const selection: MockSelection = {
            start: { line: 140, character: 0 },
            end: { line: 141, character: 0 }  // Cursor at start of line 142
        };

        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 141);
        assert.strictEqual(result.endLine, 141); // Should be just line 141
    });

    it('Selection starting at column 0, ending at column 0 - multiple lines', () => {
        // User selects from start of line 141 to start of line 144
        const selection: MockSelection = {
            start: { line: 140, character: 0 },
            end: { line: 143, character: 0 }
        };

        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 141);
        assert.strictEqual(result.endLine, 143);
    });

    it('Selection entirely within one line (single line, non-zero columns)', () => {
        // Select characters 10-30 on line 141
        const selection: MockSelection = {
            start: { line: 140, character: 10 },
            end: { line: 140, character: 30 }
        };

        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 141);
        assert.strictEqual(result.endLine, 141);
    });

    it('Edge case: selection end at column 0 but single line', () => {
        // This shouldn't happen in practice but test the logic
        // If start and end are same line, even if end.char is 0
        const selection: MockSelection = {
            start: { line: 140, character: 0 },
            end: { line: 140, character: 0 }
        };

        const result = calculateLineNumbers(selection);

        // When end.line === start.line, the condition fails, so we add 1
        assert.strictEqual(result.startLine, 141);
        assert.strictEqual(result.endLine, 141);
    });

    it('Real-world scenario: selecting def _extract_python_symbols', () => {
        // User selects lines 141-143:
        // 141: def _extract_python_symbols(self, tree: Any, code: str) -> list[Symbol]:
        // 142:     """Extract symbols from Python code."""
        // 143:     symbols: list[Symbol] = []

        // When selecting full lines in VS Code, selection will be:
        const selection: MockSelection = {
            start: { line: 140, character: 0 },  // Line 141 in 1-indexed
            end: { line: 143, character: 0 }     // Start of line 144 in 1-indexed
        };

        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 141, 'Should start at line 141');
        assert.strictEqual(result.endLine, 143, 'Should end at line 143, NOT 144');
    });

    it('Another edge case: multi-line ending with content', () => {
        // Select from line 141 to middle of line 143
        const selection: MockSelection = {
            start: { line: 140, character: 4 },
            end: { line: 142, character: 20 }  // Middle of line 143
        };

        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 141);
        assert.strictEqual(result.endLine, 143);
    });

    it('Verify the bug we fixed: lines 140-142 selected but got 141-143', () => {
        // This was the original bug - user selected lines 140-142
        // VS Code selection would be:
        const selection: MockSelection = {
            start: { line: 139, character: 0 },  // Line 140 in 1-indexed
            end: { line: 142, character: 0 }     // Start of line 143 in 1-indexed
        };

        // OLD BUGGY CODE would do:
        // startLine = 139 + 1 = 140
        // endLine = 142 + 1 = 143  <- WRONG!

        // NEW FIXED CODE should do:
        const result = calculateLineNumbers(selection);

        assert.strictEqual(result.startLine, 140, 'Should start at line 140');
        assert.strictEqual(result.endLine, 142, 'Should end at line 142, not 143');
    });
});
