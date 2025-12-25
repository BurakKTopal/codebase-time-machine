/**
 * Tests for Constants
 */

import * as assert from 'assert';
import {
    DEFAULT_MAX_TOOL_CALLS,
    getSynthesisThreshold,
    CORE_TOOLS,
    DEFAULT_PROVIDER,
    DEFAULT_MODEL
} from './constants';

describe('Constants', () => {
    describe('DEFAULT_MAX_TOOL_CALLS', () => {
        it('should be a positive number', () => {
            assert.ok(DEFAULT_MAX_TOOL_CALLS > 0);
        });

        it('should be within reasonable bounds', () => {
            assert.ok(DEFAULT_MAX_TOOL_CALLS >= 3);
            assert.ok(DEFAULT_MAX_TOOL_CALLS <= 25);
        });

        it('should be 12 by default', () => {
            assert.strictEqual(DEFAULT_MAX_TOOL_CALLS, 12);
        });
    });

    describe('getSynthesisThreshold', () => {
        it('should return 75% of max tool calls (floored)', () => {
            assert.strictEqual(getSynthesisThreshold(12), 9);
            assert.strictEqual(getSynthesisThreshold(10), 7);
            assert.strictEqual(getSynthesisThreshold(20), 15);
        });

        it('should handle edge cases', () => {
            assert.strictEqual(getSynthesisThreshold(3), 2);
            assert.strictEqual(getSynthesisThreshold(4), 3);
            assert.strictEqual(getSynthesisThreshold(1), 0);
        });

        it('should always be less than max tool calls', () => {
            for (let max = 1; max <= 25; max++) {
                const threshold = getSynthesisThreshold(max);
                assert.ok(threshold < max, `Threshold ${threshold} should be less than max ${max}`);
            }
        });
    });

    describe('CORE_TOOLS', () => {
        it('should be a non-empty array', () => {
            assert.ok(Array.isArray(CORE_TOOLS));
            assert.ok(CORE_TOOLS.length > 0);
        });

        it('should include the primary tool', () => {
            assert.ok(CORE_TOOLS.includes('get_local_line_context'));
        });

        it('should include PR and issue tools', () => {
            assert.ok(CORE_TOOLS.includes('get_pr'));
            assert.ok(CORE_TOOLS.includes('get_issue'));
        });

        it('should include file analysis tools', () => {
            assert.ok(CORE_TOOLS.includes('get_github_file_history'));
            assert.ok(CORE_TOOLS.includes('explain_file'));
        });

        it('should include code archaeology tool', () => {
            assert.ok(CORE_TOOLS.includes('pickaxe_search'));
        });

        it('should not have duplicates', () => {
            const uniqueTools = [...new Set(CORE_TOOLS)];
            assert.strictEqual(uniqueTools.length, CORE_TOOLS.length);
        });
    });

    describe('DEFAULT_PROVIDER', () => {
        it('should be anthropic', () => {
            assert.strictEqual(DEFAULT_PROVIDER, 'anthropic');
        });
    });

    describe('DEFAULT_MODEL', () => {
        it('should be a valid Claude model', () => {
            assert.ok(DEFAULT_MODEL.includes('claude'));
        });

        it('should be haiku for speed', () => {
            assert.ok(DEFAULT_MODEL.includes('haiku'));
        });
    });
});
