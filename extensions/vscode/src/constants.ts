/**
 * Shared constants for CTM VSCode Extension
 */

/**
 * Default maximum number of tool calls per investigation
 * Can be overridden via ctm.maxToolCalls setting
 */
export const DEFAULT_MAX_TOOL_CALLS = 12;

/**
 * Calculate synthesis threshold from max tool calls
 * Synthesis is triggered at ~75% of max to allow finishing touches
 */
export function getSynthesisThreshold(maxToolCalls: number): number {
    return Math.floor(maxToolCalls * 0.75);
}

/**
 * Core tools - balanced set for "why does this code exist?"
 * Not too few (missing context), not too many (token waste)
 */
export const CORE_TOOLS = [
    // === PRIMARY - Start here ===
    'get_local_line_context',   // Gets blame + PR + issues + history in ONE call

    // === Context enrichment ===
    'get_pr',                   // Full PR details with comments/reviews
    'get_issue',                // Full issue details with comments
    'search_prs_for_commit',    // Find PR from commit SHA

    // === File/commit analysis ===
    'get_github_file_history',  // File commit history
    'get_github_commits_batch', // Efficient batch commit fetching
    'explain_file',             // File overview, purpose, contributors
    'get_commit_diff',          // See actual changes in a commit

    // === Code archaeology ===
    'pickaxe_search',           // Find when code was added/removed (git -S)

    // === Ownership & context ===
    'get_code_owners',          // Who knows this code best
];

/**
 * Default provider if not configured
 * Models are now defined in providers/anthropic.ts (or other provider files)
 */
export const DEFAULT_PROVIDER = 'anthropic';

/**
 * Default model if not configured
 */
export const DEFAULT_MODEL = 'claude-3-5-haiku-20241022';
