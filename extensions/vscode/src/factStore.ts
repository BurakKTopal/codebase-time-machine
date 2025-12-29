import Anthropic from '@anthropic-ai/sdk';

/**
 * A frozen fact extracted from tool output.
 * Facts are durable, low-token representations of tool results.
 */
export interface Fact {
    id: string;           // Unique identifier (e.g., "blame_commit", "pr_163")
    text: string;         // The fact itself: "Added Feb 29 2024 by Drew Dolgert"
    source: string;       // Tool that produced this fact
    category: 'commit' | 'pr' | 'issue' | 'code' | 'author' | 'other';
}

/**
 * Verbatim evidence extracted from tool output.
 * Unlike facts (semantic summaries), evidence preserves exact details
 * like email addresses, full commit SHAs, and precise timestamps.
 *
 * Evidence is only attached during synthesis phase (≤500 tokens).
 */
export interface Evidence {
    id: string;           // Unique identifier (e.g., "author_abc123")
    type: 'email' | 'author' | 'committer' | 'timestamp' | 'sha' | 'url';
    verbatim: string;     // Exact value: "John Doe <john@example.com>"
    source: string;       // Tool that produced this
}

/**
 * Investigation state for continuation and context tracking.
 */
export interface InvestigationState {
    goal: string;
    filePath: string;
    lineRange: string;
    facts: Fact[];
    toolsCalled: string[];
    openQuestions: string[];
}

/**
 * Format an array of line numbers into compact ranges.
 * Example: [1, 2, 3, 5, 6, 10] -> "1-3, 5-6, 10"
 */
function formatLineRanges(lines: number[]): string {
    if (lines.length === 0) return '';
    if (lines.length === 1) return String(lines[0]);

    const sorted = [...lines].sort((a, b) => a - b);
    const ranges: string[] = [];
    let rangeStart = sorted[0];
    let rangeEnd = sorted[0];

    for (let i = 1; i < sorted.length; i++) {
        if (sorted[i] === rangeEnd + 1) {
            rangeEnd = sorted[i];
        } else {
            ranges.push(rangeStart === rangeEnd ? String(rangeStart) : `${rangeStart}-${rangeEnd}`);
            rangeStart = sorted[i];
            rangeEnd = sorted[i];
        }
    }
    ranges.push(rangeStart === rangeEnd ? String(rangeStart) : `${rangeStart}-${rangeEnd}`);

    return ranges.join(', ');
}

/**
 * FactStore - Token-efficient storage for investigation context.
 *
 * Extracts durable facts from tool outputs and discards the raw results.
 * This keeps context compact while preserving key information.
 */
export class FactStore {
    private facts: Map<string, Fact> = new Map();
    private evidence: Map<string, Evidence> = new Map();
    private toolsCalled: string[] = [];
    private anthropic: Anthropic;

    constructor(apiKey: string) {
        this.anthropic = new Anthropic({ apiKey, dangerouslyAllowBrowser: true });
    }

    /**
     * Extract facts and evidence from a tool result and store them.
     * Returns a SHORT confirmation (not the raw result).
     */
    async extractAndStore(toolName: string, result: any): Promise<string> {
        this.toolsCalled.push(toolName);

        // Skip extraction for empty/error results
        if (!result || result.error) {
            return `✗ ${toolName}: no data`;
        }

        // Extract facts based on tool type (deterministic, no LLM needed for structured data)
        const facts = this.extractFactsFromResult(toolName, result);

        // Extract verbatim evidence (emails, full SHAs, timestamps)
        const evidenceItems = this.extractEvidenceFromResult(toolName, result);

        // Store facts (deduplicated by ID)
        facts.forEach(f => this.facts.set(f.id, f));

        // Store evidence (deduplicated by ID)
        evidenceItems.forEach(e => this.evidence.set(e.id, e));

        console.log(`[FactStore] Extracted ${facts.length} facts, ${evidenceItems.length} evidence items from ${toolName}`);
        console.log(`[FactStore] Total: ${this.facts.size} facts, ${this.evidence.size} evidence`);

        // Return SHORT confirmation - NOT the raw result
        return `✓ ${toolName}: ${facts.length} facts extracted`;
    }

    /**
     * Extract facts from tool result - deterministic, no LLM call needed.
     * This is fast and cheap.
     */
    private extractFactsFromResult(toolName: string, result: any): Fact[] {
        const facts: Fact[] = [];

        // Handle get_local_line_context / get_line_context
        if (toolName === 'get_local_line_context' || toolName === 'get_line_context') {
            // Get GitHub base URL for constructing links
            const githubBaseUrl = result.github_remote
                ? `https://github.com/${result.github_remote.owner}/${result.github_remote.repo}`
                : null;

            // Include the interpretation note from the MCP tool (explains last-touch vs origin)
            if (result.interpretation) {
                facts.push({
                    id: 'interpretation',
                    text: result.interpretation,
                    source: toolName,
                    category: 'other'
                });
            }

            // Handle pre-analyzed code_sections (preferred - gives structured breakdown)
            if (result.code_sections && result.code_sections.length > 0) {
                // Add a structured overview for the agent
                if (result.code_sections.length > 1) {
                    const overview = result.code_sections.map((section: any) => {
                        const commitRef = section.html_url
                            ? `[${section.commit_short_sha}](${section.html_url})`
                            : section.commit_short_sha;
                        const prRef = section.pr_url && section.pr_number
                            ? ` via [PR #${section.pr_number}](${section.pr_url})`
                            : section.pr_number ? ` via PR #${section.pr_number}` : '';
                        return `• Lines ${section.line_range}: Last modified by ${commitRef} (${section.author}, ${section.date?.substring(0, 10)})${prRef}`;
                    }).join('\n');

                    facts.push({
                        id: 'code_sections_overview',
                        text: `CODE SECTIONS (last modified by):\n${overview}`,
                        source: toolName,
                        category: 'other'
                    });
                }

                // Add detailed facts for each section
                const seenPRs = new Set<number>();
                result.code_sections.forEach((section: any, idx: number) => {
                    const commitRef = section.html_url
                        ? `[${section.commit_short_sha}](${section.html_url})`
                        : section.commit_short_sha;
                    const prRef = section.pr_url && section.pr_number
                        ? ` (via [PR #${section.pr_number}](${section.pr_url}))`
                        : section.pr_number ? ` (via PR #${section.pr_number})` : '';

                    facts.push({
                        id: `section_${idx}_${section.commit_short_sha}`,
                        text: `Section ${idx + 1} (lines ${section.line_range}): Last modified by ${commitRef} (${section.author}, ${section.date?.substring(0, 10)}) - "${section.message?.split('\n')[0]?.substring(0, 60)}"${prRef}`,
                        source: toolName,
                        category: 'commit'
                    });

                    // Handle origins data from auto-pickaxe (if present)
                    // origins is now a list grouped by SHA, each with a 'lines' array
                    if (section.origins && section.origins.length > 0) {
                        for (const origin of section.origins) {
                            // Skip origins that match the last-modified commit
                            if (origin.sha === section.commit_sha) {
                                continue;
                            }

                            const originRef = origin.html_url
                                ? `[${origin.short_sha}](${origin.html_url})`
                                : origin.short_sha;

                            // Format line ranges compactly
                            const lineRanges = formatLineRanges(origin.lines || []);

                            // Build status note based on comment state
                            // introduced_as_comment is now a list of line numbers
                            let statusNote = '';
                            if (section.is_currently_commented && origin.introduced_as_comment) {
                                const commentLines = origin.introduced_as_comment as number[];
                                const allLines = origin.lines as number[];
                                if (commentLines.length === allLines.length) {
                                    // All lines were introduced as comments
                                    statusNote = ' [NOTE: was introduced as a comment/placeholder]';
                                } else if (commentLines.length === 0) {
                                    // No lines were introduced as comments
                                    statusNote = ' [NOTE: was introduced as active code, later commented out]';
                                } else {
                                    // Mixed: some lines were comments, some were active code
                                    const commentRanges = formatLineRanges(commentLines);
                                    statusNote = ` [NOTE: lines ${commentRanges} introduced as comments, others as active code]`;
                                }
                            }

                            facts.push({
                                id: `origin_${idx}_${origin.short_sha}_${origin.lines?.[0] || 0}`,
                                text: `Origin of line${origin.lines?.length > 1 ? 's' : ''} ${lineRanges}: First added by ${originRef} (${origin.author}, ${origin.date?.substring(0, 10)}) - "${origin.message}"${statusNote}`,
                                source: toolName,
                                category: 'commit'
                            });
                        }
                    }

                    // Also create PR facts for PRs found in sections (for UI display)
                    if (section.pr_number && !seenPRs.has(section.pr_number)) {
                        seenPRs.add(section.pr_number);
                        const prUrl = section.pr_url || (githubBaseUrl ? `${githubBaseUrl}/pull/${section.pr_number}` : null);
                        const prRefLink = prUrl ? `[PR #${section.pr_number}](${prUrl})` : `PR #${section.pr_number}`;
                        facts.push({
                            id: `pr_${section.pr_number}`,
                            text: `${prRefLink}: "${section.message?.split('\n')[0]?.substring(0, 80) || 'Untitled'}" by ${section.author} (from code section lines ${section.line_range})`,
                            source: toolName,
                            category: 'pr'
                        });
                    }
                });
            } else if (result.last_modified_by) {
                // Use last_modified_by (new field name)
                const bc = result.last_modified_by;
                const commitUrl = bc.html_url || (githubBaseUrl ? `${githubBaseUrl}/commit/${bc.sha}` : null);
                const commitRef = commitUrl
                    ? `[${bc.sha?.substring(0, 8)}](${commitUrl})`
                    : bc.sha?.substring(0, 8);
                facts.push({
                    id: `blame_${bc.sha?.substring(0, 8)}`,
                    text: `Last modified by ${commitRef}: ${bc.author} on ${bc.date?.substring(0, 10)} - "${bc.message?.split('\n')[0]?.substring(0, 80)}"`,
                    source: toolName,
                    category: 'commit'
                });
            } else if (result.blame_commit) {
                // Fallback to blame_commit for backwards compatibility
                const bc = result.blame_commit;
                const commitUrl = bc.html_url || (githubBaseUrl ? `${githubBaseUrl}/commit/${bc.sha}` : null);
                const commitRef = commitUrl
                    ? `[${bc.sha?.substring(0, 8)}](${commitUrl})`
                    : bc.sha?.substring(0, 8);
                facts.push({
                    id: `blame_${bc.sha?.substring(0, 8)}`,
                    text: `Last modified by ${commitRef}: ${bc.author} on ${bc.date?.substring(0, 10)} - "${bc.message?.split('\n')[0]?.substring(0, 80)}"`,
                    source: toolName,
                    category: 'commit'
                });
            }

            // PR
            if (result.pull_request) {
                const pr = result.pull_request;
                const prUrl = pr.html_url || (githubBaseUrl ? `${githubBaseUrl}/pull/${pr.number}` : null);
                const prRef = prUrl ? `[PR #${pr.number}](${prUrl})` : `PR #${pr.number}`;
                // Include state in the fact text so it can be parsed by buildRawContextFromFacts
                const stateStr = pr.state ? ` (${pr.state})` : '';
                facts.push({
                    id: `pr_${pr.number}`,
                    text: `${prRef}: "${pr.title || 'Untitled'}" by ${pr.author}${stateStr}`,
                    source: toolName,
                    category: 'pr'
                });
                if (pr.body && pr.body.length > 50) {
                    facts.push({
                        id: `pr_${pr.number}_reason`,
                        text: `${prRef} reason: ${pr.body.substring(0, 200)}...`,
                        source: toolName,
                        category: 'pr'
                    });
                }
            }

            // Linked issues
            if (result.linked_issues && result.linked_issues.length > 0) {
                result.linked_issues.forEach((issue: any) => {
                    const issueUrl = issue.html_url || (githubBaseUrl ? `${githubBaseUrl}/issues/${issue.number}` : null);
                    const issueRef = issueUrl ? `[Issue #${issue.number}](${issueUrl})` : `Issue #${issue.number}`;
                    // Include state and author in the fact text so it can be parsed by buildRawContextFromFacts
                    const stateStr = issue.state ? ` (${issue.state})` : '';
                    const authorStr = issue.author ? ` by ${issue.author}` : '';
                    // Include labels to surface bug fixes and other classifications
                    const labelsStr = issue.labels && issue.labels.length > 0
                        ? ` [${issue.labels.join(', ')}]`
                        : '';
                    facts.push({
                        id: `issue_${issue.number}`,
                        text: `${issueRef}: "${issue.title || 'Untitled'}"${authorStr}${stateStr}${labelsStr}`,
                        source: toolName,
                        category: 'issue'
                    });
                    if (issue.body && issue.body.length > 50) {
                        facts.push({
                            id: `issue_${issue.number}_desc`,
                            text: `${issueRef} problem: ${issue.body.substring(0, 150)}...`,
                            source: toolName,
                            category: 'issue'
                        });
                    }
                });
            }

            // Historical commits (when code was introduced) - INCLUDE SHAs
            if (result.historical_commits && result.historical_commits.length > 0) {
                // Store all historical commit SHAs so agent can reference them
                result.historical_commits.forEach((commit: any, _idx: number) => {
                    if (commit.sha) {
                        const commitUrl = githubBaseUrl ? `${githubBaseUrl}/commit/${commit.sha}` : null;
                        const commitRef = commitUrl
                            ? `[${commit.sha?.substring(0, 8)}](${commitUrl})`
                            : commit.sha?.substring(0, 8);
                        facts.push({
                            id: `history_${commit.sha?.substring(0, 8)}`,
                            text: `Historical commit ${commitRef}: by ${commit.author} on ${commit.date?.substring(0, 10)} - "${commit.message?.split('\n')[0]?.substring(0, 60)}"`,
                            source: toolName,
                            category: 'commit'
                        });
                    }
                });

                // Note: historical_commits is just recent file history, NOT true origin
                // True origin requires pickaxe_search - don't mislabel as ORIGIN
                const oldestSeen = result.historical_commits[result.historical_commits.length - 1];
                if (oldestSeen) {
                    const oldestUrl = githubBaseUrl ? `${githubBaseUrl}/commit/${oldestSeen.sha}` : null;
                    const oldestRef = oldestUrl
                        ? `[${oldestSeen.sha?.substring(0, 8)}](${oldestUrl})`
                        : oldestSeen.sha?.substring(0, 8);
                    facts.push({
                        id: `oldest_seen_${oldestSeen.sha?.substring(0, 8)}`,
                        text: `Oldest commit in view ${oldestRef}: by ${oldestSeen.author} on ${oldestSeen.date?.substring(0, 10)} (use pickaxe_search for true origin)`,
                        source: toolName,
                        category: 'commit'
                    });
                }
            }

            // NEW: Extract patterns_detected for quick insights
            if (result.patterns_detected && result.patterns_detected.length > 0) {
                result.patterns_detected.forEach((pattern: any) => {
                    // Make same-function pattern extra prominent
                    if (pattern.type === 'commented_alternative_same_function') {
                        facts.push({
                            id: `pattern_${pattern.type}`,
                            text: `🔴 CRITICAL: ${pattern.message}. ${pattern.hint}`,
                            source: toolName,
                            category: 'other'
                        });
                    } else {
                        facts.push({
                            id: `pattern_${pattern.type}`,
                            text: `⚠️ PATTERN: ${pattern.message}. Hint: ${pattern.hint}`,
                            source: toolName,
                            category: 'other'
                        });
                    }
                });
            }

            // NEW: Extract quick_answer for TL;DR (compact, not verbose)
            if (result.quick_answer) {
                facts.push({
                    id: 'quick_answer',
                    text: `💡 TL;DR: ${result.quick_answer}`,
                    source: toolName,
                    category: 'other'
                });
            }

            // NEW: Extract confidence scoring (compact)
            if (result.confidence) {
                const conf = result.confidence;
                facts.push({
                    id: 'confidence',
                    text: `📊 Confidence: ${conf.level} (${conf.score}/100)`,
                    source: toolName,
                    category: 'other'
                });
            }

            // NEW: Show nearby context - IMPORTANT for detecting active alternatives
            if (result.nearby_context?.after?.content) {
                const afterContent = result.nearby_context.after.content;
                const lineRange = result.nearby_context.after.lines;
                // Show more content so LLM can see the active binding
                const preview = afterContent.substring(0, 300).replace(/\n/g, '\n    ');
                facts.push({
                    id: 'nearby_context_after',
                    text: `📍 ACTIVE CODE BELOW (lines ${lineRange?.[0]}-${lineRange?.[1]}):\n    ${preview}${afterContent.length > 300 ? '...' : ''}`,
                    source: toolName,
                    category: 'code'
                });
            }
        }

        // Handle get_pr - data is nested under result.pr
        if (toolName === 'get_pr') {
            const pr = result.pr || result;
            const prUrl = pr.html_url;
            const prRef = prUrl ? `[PR #${pr.number}](${prUrl})` : `PR #${pr.number}`;
            facts.push({
                id: `pr_${pr.number}`,
                text: `${prRef}: "${pr.title}" by ${pr.author} (${pr.state})`,
                source: toolName,
                category: 'pr'
            });
            if (pr.body) {
                facts.push({
                    id: `pr_${pr.number}_body`,
                    text: `${prRef} description: ${pr.body.substring(0, 300)}...`,
                    source: toolName,
                    category: 'pr'
                });
            }
            if (pr.comments && pr.comments.length > 0) {
                const keyComment = pr.comments.find((c: any) => c.body && c.body.length > 50);
                if (keyComment) {
                    facts.push({
                        id: `pr_${pr.number}_discussion`,
                        text: `${prRef} discussion: @${keyComment.author}: "${keyComment.body.substring(0, 150)}..."`,
                        source: toolName,
                        category: 'pr'
                    });
                }
            }
        }

        // Handle get_issue - data is nested under result.issue
        if (toolName === 'get_issue') {
            const issue = result.issue || result;
            const issueUrl = issue.html_url;
            const issueRef = issueUrl ? `[Issue #${issue.number}](${issueUrl})` : `Issue #${issue.number}`;
            // Include labels to surface bug fixes and other classifications
            const labels = issue.labels || [];
            const labelNames = labels.map((l: any) => typeof l === 'string' ? l : l.name).filter(Boolean);
            const labelsStr = labelNames.length > 0 ? ` [${labelNames.join(', ')}]` : '';
            facts.push({
                id: `issue_${issue.number}`,
                text: `${issueRef}: "${issue.title}" by ${issue.author} (${issue.state})${labelsStr}`,
                source: toolName,
                category: 'issue'
            });
            if (issue.body) {
                facts.push({
                    id: `issue_${issue.number}_body`,
                    text: `${issueRef} problem: ${issue.body.substring(0, 300)}...`,
                    source: toolName,
                    category: 'issue'
                });
            }
        }

        // Handle get_commit / get_github_commit - INCLUDE FULL SHA
        if (toolName === 'get_commit' || toolName === 'get_github_commit') {
            const commit = result.commit || result;
            const commitUrl = commit.html_url;
            const commitRef = commitUrl
                ? `[${commit.sha?.substring(0, 8)}](${commitUrl})`
                : commit.sha?.substring(0, 8);
            facts.push({
                id: `commit_${commit.sha?.substring(0, 8)}`,
                text: `Commit ${commitRef}: by ${commit.author?.name || commit.author} on ${commit.authored_date?.substring(0, 10) || commit.date?.substring(0, 10)} - "${commit.message?.split('\n')[0]?.substring(0, 80)}"`,
                source: toolName,
                category: 'commit'
            });
            // Also store PR number if present
            if (commit.pr_number) {
                // Construct PR URL from commit URL if available
                const prUrl = commitUrl ? commitUrl.replace(/\/commit\/[^/]+$/, `/pull/${commit.pr_number}`) : null;
                const prRef = prUrl ? `[PR #${commit.pr_number}](${prUrl})` : `PR #${commit.pr_number}`;
                facts.push({
                    id: `commit_pr_${commit.pr_number}`,
                    text: `Commit ${commitRef} is from ${prRef}`,
                    source: toolName,
                    category: 'pr'
                });
            }
        }

        // Handle search_prs_for_commit - returns prs array with full details
        if (toolName === 'search_prs_for_commit') {
            const prs = result.prs || [];
            const prNumbers = result.pr_numbers || [];

            if (prs.length > 0) {
                // Extract full PR details with hyperlinks
                // Only create full PR facts if we have actual title/state info
                prs.forEach((pr: any) => {
                    const prRef = pr.html_url
                        ? `[PR #${pr.number}](${pr.html_url})`
                        : `PR #${pr.number}`;

                    // If PR has actual details (title not null), create full fact
                    if (pr.title) {
                        const stateStr = pr.state ? ` (${pr.state})` : '';
                        facts.push({
                            id: `pr_${pr.number}`,
                            text: `${prRef}: "${pr.title}" by ${pr.author || 'unknown'}${stateStr}`,
                            source: toolName,
                            category: 'pr'
                        });
                        if (pr.body && pr.body.length > 20) {
                            facts.push({
                                id: `pr_${pr.number}_body`,
                                text: `${prRef} description: ${pr.body.substring(0, 200)}...`,
                                source: toolName,
                                category: 'pr'
                            });
                        }
                    } else {
                        // PR has incomplete data - just note its existence, don't create pr_XXX fact
                        // This prevents incomplete PRs from being picked up by buildRawContextFromFacts
                        facts.push({
                            id: `pr_ref_${pr.number}`,
                            text: `Found ${prRef} (details not available - use get_pr for full info)`,
                            source: toolName,
                            category: 'other'  // Use 'other' instead of 'pr' to avoid UI picking it up
                        });
                    }
                });
            } else if (prNumbers.length > 0) {
                // Fallback to just PR numbers if full details not available
                facts.push({
                    id: `search_prs_${result.sha?.substring(0, 8)}`,
                    text: `Commit ${result.sha?.substring(0, 8)} is associated with PR(s): ${prNumbers.map((n: number) => `#${n}`).join(', ')} (use get_pr for details)`,
                    source: toolName,
                    category: 'other'  // Use 'other' to avoid incomplete PRs in UI
                });
            }
        }

        // Handle file history - INCLUDE SHAs for each commit
        if ((toolName === 'get_github_file_history' || toolName === 'trace_file_history') && result.commits) {
            // Store individual commit SHAs so agent can use them
            result.commits.slice(0, 5).forEach((c: any) => {
                facts.push({
                    id: `file_commit_${c.sha?.substring(0, 8)}`,
                    text: `File commit ${c.sha}: "${c.message?.split('\n')[0]?.substring(0, 60)}"`,
                    source: toolName,
                    category: 'commit'
                });
            });

            // Summary
            facts.push({
                id: 'file_history_summary',
                text: `File has ${result.commits.length} total commits`,
                source: toolName,
                category: 'other'
            });
        }

        // Handle pickaxe_search - finds when code was added/removed
        if (toolName === 'pickaxe_search') {
            if (result.commits && result.commits.length > 0) {
                result.commits.forEach((c: any) => {
                    // Format commit with hyperlink if URL available
                    const commitRef = c.html_url
                        ? `[${c.sha?.substring(0, 8)}](${c.html_url})`
                        : c.sha?.substring(0, 8);
                    const prRef = c.pr_url && c.pr_number
                        ? ` (via [PR #${c.pr_number}](${c.pr_url}))`
                        : c.pr_number ? ` (via PR #${c.pr_number})` : '';

                    facts.push({
                        id: `pickaxe_${c.sha?.substring(0, 8)}`,
                        text: `Pickaxe found commit ${commitRef}: by ${c.author} on ${c.date?.substring(0, 10)} - "${c.message?.split('\n')[0]?.substring(0, 80)}"${prRef}`,
                        source: toolName,
                        category: 'commit'
                    });
                });

                // Use introduction_commit (oldest = true origin), NOT commits[0] (newest)
                // The MCP server returns commits newest→oldest, with introduction_commit being the oldest
                const origin = result.introduction_commit || result.commits[result.commits.length - 1];
                const originRef = origin.html_url
                    ? `[${origin.sha?.substring(0, 8)}](${origin.html_url})`
                    : origin.sha?.substring(0, 8);
                const originPrRef = origin.pr_url && origin.pr_number
                    ? ` (via [PR #${origin.pr_number}](${origin.pr_url}))`
                    : origin.pr_number ? ` (via PR #${origin.pr_number})` : '';

                facts.push({
                    id: `pickaxe_origin`,
                    text: `ORIGIN: Code "${result.search_string || 'pattern'}" first added in commit ${originRef} by ${origin.author} on ${origin.date?.substring(0, 10)}${originPrRef}`,
                    source: toolName,
                    category: 'commit'
                });

                // Also store as proper origin fact for buildRawContextFromFacts
                facts.push({
                    id: `origin_${origin.sha?.substring(0, 8)}`,
                    text: `ORIGIN commit ${originRef}: Code first added by ${origin.author} on ${origin.date?.substring(0, 10)}${originPrRef}`,
                    source: toolName,
                    category: 'commit'
                });
            } else {
                facts.push({
                    id: 'pickaxe_no_results',
                    text: `Pickaxe search for "${result.search_string || 'pattern'}" found no commits`,
                    source: toolName,
                    category: 'other'
                });
            }
        }

        // Handle get_code_owners - who knows this code best
        if (toolName === 'get_code_owners') {
            if (result.owners && result.owners.length > 0) {
                // Summary of top contributors
                const topOwners = result.owners.slice(0, 3);
                const ownersSummary = topOwners.map((o: any) =>
                    `${o.name} (${o.commits} commits, ${o.commit_percentage}%, last: ${o.last_commit_date?.substring(0, 10)})`
                ).join('; ');

                facts.push({
                    id: `code_owners_${result.path?.replace(/[^a-z0-9]/gi, '_')}`,
                    text: `Code owners for ${result.path}: ${ownersSummary}`,
                    source: toolName,
                    category: 'other'
                });

                // Primary owner with more details
                const primary = result.owners[0];
                facts.push({
                    id: `primary_owner_${result.path?.replace(/[^a-z0-9]/gi, '_')}`,
                    text: `Primary code owner: ${primary.name} (${primary.email}) with ${primary.commits} commits (${primary.commit_percentage}% ownership, score: ${primary.ownership_score})`,
                    source: toolName,
                    category: 'other'
                });

                // Store all owner emails as evidence for potential contact
                result.owners.forEach((owner: any) => {
                    if (owner.email) {
                        facts.push({
                            id: `owner_contact_${owner.name?.replace(/[^a-z0-9]/gi, '_')}`,
                            text: `Contact for ${owner.name}: ${owner.email}`,
                            source: toolName,
                            category: 'other'
                        });
                    }
                });
            }

            // Overall stats
            if (result.total_commits_analyzed) {
                facts.push({
                    id: `code_owners_stats`,
                    text: `Code ownership analysis: ${result.unique_contributors || 'unknown'} unique contributors across ${result.total_commits_analyzed} commits`,
                    source: toolName,
                    category: 'other'
                });
            }
        }

        // Handle get_commit_diff - shows actual changes in a commit
        if (toolName === 'get_commit_diff') {
            const sha = result.sha || result.commit?.sha;
            if (result.files && result.files.length > 0) {
                // Summary of files changed
                const fileNames = result.files.map((f: any) => f.filename || f.path).slice(0, 5);
                facts.push({
                    id: `diff_files_${sha?.substring(0, 8)}`,
                    text: `Commit ${sha} modified: ${fileNames.join(', ')}${result.files.length > 5 ? ` (+${result.files.length - 5} more)` : ''}`,
                    source: toolName,
                    category: 'commit'
                });

                // Extract key changes from patch if present
                result.files.forEach((f: any) => {
                    if (f.patch && f.patch.length > 0) {
                        // Extract added lines (lines starting with +)
                        const addedLines = f.patch.split('\n')
                            .filter((line: string) => line.startsWith('+') && !line.startsWith('+++'))
                            .slice(0, 3)
                            .map((line: string) => line.substring(1).trim())
                            .filter((line: string) => line.length > 5);

                        if (addedLines.length > 0) {
                            facts.push({
                                id: `diff_added_${sha?.substring(0, 8)}_${f.filename?.substring(0, 20)}`,
                                text: `Added in ${f.filename || f.path}: ${addedLines.join(' | ').substring(0, 150)}`,
                                source: toolName,
                                category: 'code'
                            });
                        }
                    }
                });
            }

            // Include commit message if present
            if (result.message || result.commit?.message) {
                const msg = result.message || result.commit?.message;
                facts.push({
                    id: `diff_message_${sha?.substring(0, 8)}`,
                    text: `Commit ${sha} message: "${msg.split('\n')[0].substring(0, 100)}"`,
                    source: toolName,
                    category: 'commit'
                });
            }
        }

        return facts;
    }

    /**
     * Extract verbatim evidence from tool result.
     * Captures exact details like emails, full SHAs, precise timestamps.
     * This is separate from facts to enable precision answers.
     */
    private extractEvidenceFromResult(toolName: string, result: any): Evidence[] {
        const evidence: Evidence[] = [];

        // Helper to extract author with email
        const extractAuthor = (author: any, id: string): void => {
            if (!author) return;

            // Handle string format: "Name <email>"
            if (typeof author === 'string') {
                evidence.push({
                    id,
                    type: 'author',
                    verbatim: author,
                    source: toolName
                });
                return;
            }

            // Handle object format: { name, email }
            if (author.email) {
                const verbatim = author.name
                    ? `${author.name} <${author.email}>`
                    : author.email;
                evidence.push({
                    id,
                    type: 'author',
                    verbatim,
                    source: toolName
                });
            } else if (author.name) {
                evidence.push({
                    id,
                    type: 'author',
                    verbatim: author.name,
                    source: toolName
                });
            }
        };

        // Handle get_local_line_context / get_line_context
        if (toolName === 'get_local_line_context' || toolName === 'get_line_context') {
            // Blame commit author
            if (result.blame_commit) {
                const bc = result.blame_commit;
                if (bc.sha) {
                    evidence.push({
                        id: `sha_blame_${bc.sha.substring(0, 8)}`,
                        type: 'sha',
                        verbatim: bc.sha,
                        source: toolName
                    });
                }
                extractAuthor(bc.author_email ? { name: bc.author, email: bc.author_email } : bc.author,
                    `author_blame_${bc.sha?.substring(0, 8)}`);
                if (bc.date) {
                    evidence.push({
                        id: `timestamp_blame_${bc.sha?.substring(0, 8)}`,
                        type: 'timestamp',
                        verbatim: bc.date,
                        source: toolName
                    });
                }
            }

            // PR author
            if (result.pull_request) {
                const pr = result.pull_request;
                if (pr.author) {
                    evidence.push({
                        id: `author_pr_${pr.number}`,
                        type: 'author',
                        verbatim: typeof pr.author === 'string' ? pr.author : pr.author.login || pr.author.name,
                        source: toolName
                    });
                }
                if (pr.html_url || pr.url) {
                    evidence.push({
                        id: `url_pr_${pr.number}`,
                        type: 'url',
                        verbatim: pr.html_url || pr.url,
                        source: toolName
                    });
                }
            }

            // Historical commits
            if (result.historical_commits) {
                result.historical_commits.forEach((commit: any) => {
                    if (commit.sha) {
                        evidence.push({
                            id: `sha_history_${commit.sha.substring(0, 8)}`,
                            type: 'sha',
                            verbatim: commit.sha,
                            source: toolName
                        });
                    }
                    extractAuthor(
                        commit.author_email ? { name: commit.author, email: commit.author_email } : commit.author,
                        `author_history_${commit.sha?.substring(0, 8)}`
                    );
                });
            }
        }

        // Handle get_pr - data is nested under result.pr
        if (toolName === 'get_pr') {
            const pr = result.pr || result;
            if (pr.author) {
                evidence.push({
                    id: `author_pr_${pr.number}`,
                    type: 'author',
                    verbatim: typeof pr.author === 'string' ? pr.author : pr.author.login,
                    source: toolName
                });
            }
            if (pr.html_url) {
                evidence.push({
                    id: `url_pr_${pr.number}`,
                    type: 'url',
                    verbatim: pr.html_url,
                    source: toolName
                });
            }
            if (pr.created_at) {
                evidence.push({
                    id: `timestamp_pr_${pr.number}`,
                    type: 'timestamp',
                    verbatim: pr.created_at,
                    source: toolName
                });
            }
        }

        // Handle get_issue - data is nested under result.issue
        if (toolName === 'get_issue') {
            const issue = result.issue || result;
            if (issue.author) {
                evidence.push({
                    id: `author_issue_${issue.number}`,
                    type: 'author',
                    verbatim: typeof issue.author === 'string' ? issue.author : issue.author.login,
                    source: toolName
                });
            }
            if (issue.html_url) {
                evidence.push({
                    id: `url_issue_${issue.number}`,
                    type: 'url',
                    verbatim: issue.html_url,
                    source: toolName
                });
            }
        }

        // Handle get_commit / get_github_commit
        if (toolName === 'get_commit' || toolName === 'get_github_commit') {
            const commit = result.commit || result;
            if (commit.sha) {
                evidence.push({
                    id: `sha_commit_${commit.sha.substring(0, 8)}`,
                    type: 'sha',
                    verbatim: commit.sha,
                    source: toolName
                });
            }
            // Author with email
            if (commit.author) {
                extractAuthor(commit.author, `author_commit_${commit.sha?.substring(0, 8)}`);
            }
            // Committer (if different)
            if (commit.committer && commit.committer.email !== commit.author?.email) {
                extractAuthor(commit.committer, `committer_commit_${commit.sha?.substring(0, 8)}`);
            }
            if (commit.authored_date || commit.date) {
                evidence.push({
                    id: `timestamp_commit_${commit.sha?.substring(0, 8)}`,
                    type: 'timestamp',
                    verbatim: commit.authored_date || commit.date,
                    source: toolName
                });
            }
        }

        // Handle file history
        if ((toolName === 'get_github_file_history' || toolName === 'trace_file_history') && result.commits) {
            result.commits.slice(0, 5).forEach((c: any) => {
                if (c.sha) {
                    evidence.push({
                        id: `sha_filehistory_${c.sha.substring(0, 8)}`,
                        type: 'sha',
                        verbatim: c.sha,
                        source: toolName
                    });
                }
                extractAuthor(c.author, `author_filehistory_${c.sha?.substring(0, 8)}`);
            });
        }

        // Handle pickaxe_search
        if (toolName === 'pickaxe_search' && result.commits) {
            result.commits.forEach((c: any) => {
                if (c.sha) {
                    evidence.push({
                        id: `sha_pickaxe_${c.sha.substring(0, 8)}`,
                        type: 'sha',
                        verbatim: c.sha,
                        source: toolName
                    });
                }
                extractAuthor(c.author, `author_pickaxe_${c.sha?.substring(0, 8)}`);
                if (c.date) {
                    evidence.push({
                        id: `timestamp_pickaxe_${c.sha?.substring(0, 8)}`,
                        type: 'timestamp',
                        verbatim: c.date,
                        source: toolName
                    });
                }
            });

            // Specifically extract the introduction_commit (true origin) as special evidence
            const origin = result.introduction_commit || result.commits[result.commits.length - 1];
            if (origin) {
                if (origin.sha) {
                    evidence.push({
                        id: `sha_origin`,
                        type: 'sha',
                        verbatim: origin.sha,
                        source: toolName
                    });
                }
                extractAuthor(origin.author, `author_origin`);
                if (origin.date) {
                    evidence.push({
                        id: `timestamp_origin`,
                        type: 'timestamp',
                        verbatim: origin.date,
                        source: toolName
                    });
                }
            }
        }

        // Handle search_prs_for_commit - extract URL and author evidence from full PR details
        if (toolName === 'search_prs_for_commit' && result.prs) {
            result.prs.forEach((pr: any) => {
                if (pr.html_url) {
                    evidence.push({
                        id: `url_pr_${pr.number}`,
                        type: 'url',
                        verbatim: pr.html_url,
                        source: toolName
                    });
                }
                if (pr.author) {
                    evidence.push({
                        id: `author_pr_${pr.number}`,
                        type: 'author',
                        verbatim: pr.author,
                        source: toolName
                    });
                }
                if (pr.merged_at) {
                    evidence.push({
                        id: `timestamp_pr_${pr.number}_merged`,
                        type: 'timestamp',
                        verbatim: pr.merged_at,
                        source: toolName
                    });
                }
            });
        }

        // Handle get_code_owners - extract emails and names as evidence
        if (toolName === 'get_code_owners' && result.owners) {
            result.owners.forEach((owner: any, idx: number) => {
                if (owner.email) {
                    evidence.push({
                        id: `email_owner_${idx}`,
                        type: 'email',
                        verbatim: owner.email,
                        source: toolName
                    });
                }
                if (owner.name) {
                    evidence.push({
                        id: `author_owner_${idx}`,
                        type: 'author',
                        verbatim: owner.name,
                        source: toolName
                    });
                }
                if (owner.last_commit_date) {
                    evidence.push({
                        id: `timestamp_owner_${idx}`,
                        type: 'timestamp',
                        verbatim: owner.last_commit_date,
                        source: toolName
                    });
                }
            });
        }

        // Handle get_commit_diff
        if (toolName === 'get_commit_diff') {
            const sha = result.sha || result.commit?.sha;
            if (sha) {
                evidence.push({
                    id: `sha_diff_${sha.substring(0, 8)}`,
                    type: 'sha',
                    verbatim: sha,
                    source: toolName
                });
            }
            if (result.author) {
                extractAuthor(result.author, `author_diff_${sha?.substring(0, 8)}`);
            }
        }

        return evidence;
    }

    /**
     * Get all facts as a compact string for the model.
     */
    getFactsSummary(): string {
        if (this.facts.size === 0) {
            return 'No facts gathered yet.';
        }

        const factsByCategory = new Map<string, Fact[]>();
        this.facts.forEach(f => {
            if (!factsByCategory.has(f.category)) {
                factsByCategory.set(f.category, []);
            }
            factsByCategory.get(f.category)!.push(f);
        });

        const lines: string[] = [];

        // Group by category for readability
        if (factsByCategory.has('commit')) {
            lines.push('**Commits:**');
            factsByCategory.get('commit')!.forEach(f => lines.push(`- ${f.text}`));
        }
        if (factsByCategory.has('pr')) {
            lines.push('**Pull Requests:**');
            factsByCategory.get('pr')!.forEach(f => lines.push(`- ${f.text}`));
        }
        if (factsByCategory.has('issue')) {
            lines.push('**Issues:**');
            factsByCategory.get('issue')!.forEach(f => lines.push(`- ${f.text}`));
        }
        if (factsByCategory.has('author')) {
            lines.push('**Authors:**');
            factsByCategory.get('author')!.forEach(f => lines.push(`- ${f.text}`));
        }
        if (factsByCategory.has('code')) {
            lines.push('**Code Changes:**');
            factsByCategory.get('code')!.forEach(f => lines.push(`- ${f.text}`));
        }
        if (factsByCategory.has('other')) {
            lines.push('**Other:**');
            factsByCategory.get('other')!.forEach(f => lines.push(`- ${f.text}`));
        }

        return lines.join('\n');
    }

    /**
     * Get the current investigation state.
     */
    getState(goal: string, filePath: string, lineRange: string): InvestigationState {
        return {
            goal,
            filePath,
            lineRange,
            facts: Array.from(this.facts.values()),
            toolsCalled: [...this.toolsCalled],
            openQuestions: this.identifyOpenQuestions()
        };
    }

    /**
     * Identify what we still don't know.
     */
    private identifyOpenQuestions(): string[] {
        const questions: string[] = [];

        const hasBlame = Array.from(this.facts.values()).some(f => f.id.startsWith('blame_'));
        const hasPR = Array.from(this.facts.values()).some(f => f.id.startsWith('pr_'));
        const hasIssue = Array.from(this.facts.values()).some(f => f.id.startsWith('issue_'));
        const hasOrigin = Array.from(this.facts.values()).some(f => f.id.startsWith('origin_'));

        if (!hasBlame) questions.push('Who last modified this code?');
        if (!hasPR) questions.push('What PR introduced this change?');
        if (!hasIssue) questions.push('What issue or problem did this solve?');
        if (!hasOrigin) questions.push('When was this code originally added?');

        return questions;
    }

    /**
     * Check if we have enough context to synthesize.
     */
    hasEnoughContext(): boolean {
        const hasBlame = Array.from(this.facts.values()).some(f => f.id.startsWith('blame_') || f.id.startsWith('origin_'));
        const hasPROrIssue = Array.from(this.facts.values()).some(f => f.id.startsWith('pr_') || f.id.startsWith('issue_'));

        // We have enough if we know who wrote it AND why (PR or issue)
        return hasBlame && hasPROrIssue;
    }

    /**
     * Get tiered summary: TL;DR, key insights, and full details.
     * This helps the agent lead with the answer.
     */
    getTieredSummary(): { tldr: string | null; keyInsights: string[]; details: string } {
        const facts = Array.from(this.facts.values());

        // TL;DR: Use quick_answer if available
        const quickAnswerFact = facts.find(f => f.id === 'quick_answer');
        const tldr = quickAnswerFact
            ? quickAnswerFact.text.replace('💡 SUGGESTED TL;DR: ', '')
            : null;

        // Key Insights: Most important facts (max 5)
        const keyInsights: string[] = [];

        // 1. Patterns detected (highest priority)
        const patternFacts = facts.filter(f => f.id.startsWith('pattern_'));
        patternFacts.forEach(f => keyInsights.push(f.text));

        // 2. Confidence signals
        const confidenceFact = facts.find(f => f.id === 'confidence');
        if (confidenceFact) {
            keyInsights.push(confidenceFact.text);
        }

        // 3. Origin (when code was first added)
        const originFact = facts.find(f => f.id.startsWith('origin_'));
        if (originFact) {
            keyInsights.push(originFact.text);
        }

        // 4. PR or Issue context
        const prFact = facts.find(f => f.id.startsWith('pr_') && !f.id.includes('_reason') && !f.id.includes('_body'));
        if (prFact) {
            keyInsights.push(prFact.text);
        }

        const issueFact = facts.find(f => f.id.startsWith('issue_') && !f.id.includes('_desc') && !f.id.includes('_body'));
        if (issueFact) {
            keyInsights.push(issueFact.text);
        }

        // 5. Nearby context if relevant
        const nearbyFact = facts.find(f => f.id === 'nearby_context_after');
        if (nearbyFact) {
            keyInsights.push(nearbyFact.text);
        }

        // Full details
        const details = this.getFactsSummary();

        return {
            tldr,
            keyInsights: keyInsights.slice(0, 6),
            details
        };
    }

    /**
     * Get tools that have been called.
     */
    getToolsCalled(): string[] {
        return [...this.toolsCalled];
    }

    /**
     * Get fact count.
     */
    getFactCount(): number {
        return this.facts.size;
    }

    /**
     * Get evidence count.
     */
    getEvidenceCount(): number {
        return this.evidence.size;
    }

    /**
     * Get verbatim evidence summary for synthesis phase.
     * This is a compact (≤500 tokens) bundle of exact details.
     * Only use this during synthesis - not during investigation.
     */
    getEvidenceSummary(): string {
        if (this.evidence.size === 0) {
            return '';
        }

        const byType = new Map<string, Evidence[]>();
        this.evidence.forEach(e => {
            if (!byType.has(e.type)) {
                byType.set(e.type, []);
            }
            byType.get(e.type)!.push(e);
        });

        const lines: string[] = ['**Verbatim Evidence (for precision answers):**'];

        // Authors/Committers with emails
        if (byType.has('author')) {
            lines.push('Authors:');
            // Deduplicate by verbatim value
            const unique = new Map<string, Evidence>();
            byType.get('author')!.forEach(e => unique.set(e.verbatim, e));
            unique.forEach(e => lines.push(`  - ${e.verbatim}`));
        }

        if (byType.has('committer')) {
            lines.push('Committers:');
            const unique = new Map<string, Evidence>();
            byType.get('committer')!.forEach(e => unique.set(e.verbatim, e));
            unique.forEach(e => lines.push(`  - ${e.verbatim}`));
        }

        // Full SHAs
        if (byType.has('sha')) {
            lines.push('Full Commit SHAs:');
            byType.get('sha')!.slice(0, 10).forEach(e => {
                // Extract short ID from evidence ID for reference
                const shortId = e.id.split('_').pop();
                lines.push(`  - ${shortId}: ${e.verbatim}`);
            });
        }

        // URLs (PRs, Issues)
        if (byType.has('url')) {
            lines.push('Links:');
            byType.get('url')!.forEach(e => lines.push(`  - ${e.verbatim}`));
        }

        // Timestamps
        if (byType.has('timestamp')) {
            lines.push('Timestamps:');
            byType.get('timestamp')!.slice(0, 5).forEach(e => {
                const ref = e.id.replace('timestamp_', '');
                lines.push(`  - ${ref}: ${e.verbatim}`);
            });
        }

        return lines.join('\n');
    }

    /**
     * Clear all facts and evidence (for new investigation).
     */
    clear(): void {
        this.facts.clear();
        this.evidence.clear();
        this.toolsCalled = [];
    }
}
