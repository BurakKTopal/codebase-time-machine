/**
 * Shared constants for CTM VSCode Extension
 */

/**
 * Maximum number of tool calls per investigation
 * Reduced from 12 - we need fewer calls with better context
 */
export const MAX_TOOL_CALLS = 8;

/**
 * Threshold at which to consider synthesis
 * If context quality is good after this many calls, synthesize
 */
export const SYNTHESIS_THRESHOLD = 6;

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
 * Available Claude models for selection
 */
export const AVAILABLE_MODELS = [
    {
        id: 'claude-3-5-haiku-20241022',
        label: 'Haiku 3.5',
        description: 'Fast and cost-effective'
    },
    {
        id: 'claude-haiku-4-5-20251001',
        label: 'Haiku 4.5',
        description: 'Improved speed and efficiency'
    },
    {
        id: 'claude-sonnet-4-20250514',
        label: 'Sonnet 4',
        description: 'Balanced performance'
    },
    {
        id: 'claude-sonnet-4-5-20250929',
        label: 'Sonnet 4.5',
        description: 'Enhanced balanced performance'
    },
    {
        id: 'claude-opus-4-20250514',
        label: 'Opus 4',
        description: 'Most capable'
    },
    {
        id: 'claude-opus-4-5-20251101',
        label: 'Opus 4.5',
        description: 'Most advanced and intelligent'
    }
];

/**
 * Default model if not configured
 */
export const DEFAULT_MODEL = 'claude-3-5-haiku-20241022';
