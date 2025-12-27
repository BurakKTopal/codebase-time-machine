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
    type: 'author' | 'committer' | 'timestamp' | 'sha' | 'url';
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
            // Blame commit - INCLUDE SHA so agent can reference it
            if (result.blame_commit) {
                const bc = result.blame_commit;
                facts.push({
                    id: `blame_${bc.sha?.substring(0, 8)}`,
                    text: `Blame commit ${bc.sha}: by ${bc.author} on ${bc.date?.substring(0, 10)} - "${bc.message?.split('\n')[0]?.substring(0, 80)}"`,
                    source: toolName,
                    category: 'commit'
                });
            }

            // PR
            if (result.pull_request) {
                const pr = result.pull_request;
                // Include state in the fact text so it can be parsed by buildRawContextFromFacts
                const stateStr = pr.state ? ` (${pr.state})` : '';
                facts.push({
                    id: `pr_${pr.number}`,
                    text: `PR #${pr.number}: "${pr.title || 'Untitled'}" by ${pr.author}${stateStr}`,
                    source: toolName,
                    category: 'pr'
                });
                if (pr.body && pr.body.length > 50) {
                    facts.push({
                        id: `pr_${pr.number}_reason`,
                        text: `PR #${pr.number} reason: ${pr.body.substring(0, 200)}...`,
                        source: toolName,
                        category: 'pr'
                    });
                }
            }

            // Linked issues
            if (result.linked_issues && result.linked_issues.length > 0) {
                result.linked_issues.forEach((issue: any) => {
                    // Include state in the fact text so it can be parsed by buildRawContextFromFacts
                    const stateStr = issue.state ? ` (${issue.state})` : '';
                    facts.push({
                        id: `issue_${issue.number}`,
                        text: `Issue #${issue.number}: "${issue.title || 'Untitled'}"${stateStr}`,
                        source: toolName,
                        category: 'issue'
                    });
                    if (issue.body && issue.body.length > 50) {
                        facts.push({
                            id: `issue_${issue.number}_desc`,
                            text: `Issue #${issue.number} problem: ${issue.body.substring(0, 150)}...`,
                            source: toolName,
                            category: 'issue'
                        });
                    }
                });
            }

            // Historical commits (when code was introduced) - INCLUDE SHAs
            if (result.historical_commits && result.historical_commits.length > 0) {
                // Store all historical commit SHAs so agent can reference them
                result.historical_commits.forEach((commit: any, idx: number) => {
                    if (commit.sha) {
                        facts.push({
                            id: `history_${commit.sha?.substring(0, 8)}`,
                            text: `Historical commit ${commit.sha}: by ${commit.author} on ${commit.date?.substring(0, 10)} - "${commit.message?.split('\n')[0]?.substring(0, 60)}"`,
                            source: toolName,
                            category: 'commit'
                        });
                    }
                });

                // Mark the oldest as the origin
                const firstCommit = result.historical_commits[result.historical_commits.length - 1];
                if (firstCommit) {
                    facts.push({
                        id: `origin_${firstCommit.sha?.substring(0, 8)}`,
                        text: `ORIGIN commit ${firstCommit.sha}: Code first added by ${firstCommit.author} on ${firstCommit.date?.substring(0, 10)}`,
                        source: toolName,
                        category: 'commit'
                    });
                }
            }
        }

        // Handle get_pr - data is nested under result.pr
        if (toolName === 'get_pr') {
            const pr = result.pr || result;
            facts.push({
                id: `pr_${pr.number}`,
                text: `PR #${pr.number}: "${pr.title}" by ${pr.author} (${pr.state})`,
                source: toolName,
                category: 'pr'
            });
            if (pr.body) {
                facts.push({
                    id: `pr_${pr.number}_body`,
                    text: `PR #${pr.number} description: ${pr.body.substring(0, 300)}...`,
                    source: toolName,
                    category: 'pr'
                });
            }
            if (pr.comments && pr.comments.length > 0) {
                const keyComment = pr.comments.find((c: any) => c.body && c.body.length > 50);
                if (keyComment) {
                    facts.push({
                        id: `pr_${pr.number}_discussion`,
                        text: `PR discussion: @${keyComment.author}: "${keyComment.body.substring(0, 150)}..."`,
                        source: toolName,
                        category: 'pr'
                    });
                }
            }
        }

        // Handle get_issue - data is nested under result.issue
        if (toolName === 'get_issue') {
            const issue = result.issue || result;
            facts.push({
                id: `issue_${issue.number}`,
                text: `Issue #${issue.number}: "${issue.title}" by ${issue.author} (${issue.state})`,
                source: toolName,
                category: 'issue'
            });
            if (issue.body) {
                facts.push({
                    id: `issue_${issue.number}_body`,
                    text: `Issue #${issue.number} problem: ${issue.body.substring(0, 300)}...`,
                    source: toolName,
                    category: 'issue'
                });
            }
        }

        // Handle get_commit / get_github_commit - INCLUDE FULL SHA
        if (toolName === 'get_commit' || toolName === 'get_github_commit') {
            const commit = result.commit || result;
            facts.push({
                id: `commit_${commit.sha?.substring(0, 8)}`,
                text: `Commit ${commit.sha}: by ${commit.author?.name || commit.author} on ${commit.authored_date?.substring(0, 10) || commit.date?.substring(0, 10)} - "${commit.message?.split('\n')[0]?.substring(0, 80)}"`,
                source: toolName,
                category: 'commit'
            });
            // Also store PR number if present
            if (commit.pr_number) {
                facts.push({
                    id: `commit_pr_${commit.pr_number}`,
                    text: `Commit ${commit.sha?.substring(0, 8)} is from PR #${commit.pr_number}`,
                    source: toolName,
                    category: 'pr'
                });
            }
        }

        // Handle search_prs_for_commit - returns pr_numbers array of integers
        if (toolName === 'search_prs_for_commit') {
            const prNumbers = result.pr_numbers || [];
            if (prNumbers.length > 0) {
                // Record that we found PRs for this commit
                facts.push({
                    id: `search_prs_${result.sha?.substring(0, 8)}`,
                    text: `Commit ${result.sha?.substring(0, 8)} is associated with PR(s): ${prNumbers.map((n: number) => `#${n}`).join(', ')}`,
                    source: toolName,
                    category: 'pr'
                });
                // Also record individual PR numbers for reference
                prNumbers.forEach((prNum: number) => {
                    facts.push({
                        id: `pr_found_${prNum}`,
                        text: `Found PR #${prNum} associated with commit ${result.sha?.substring(0, 8)}`,
                        source: toolName,
                        category: 'pr'
                    });
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
                    facts.push({
                        id: `pickaxe_${c.sha?.substring(0, 8)}`,
                        text: `Pickaxe found commit ${c.sha}: by ${c.author} on ${c.date?.substring(0, 10)} - "${c.message?.split('\n')[0]?.substring(0, 80)}"`,
                        source: toolName,
                        category: 'commit'
                    });
                });

                // Mark the first result as most likely the origin
                const first = result.commits[0];
                facts.push({
                    id: `pickaxe_origin`,
                    text: `PICKAXE: Code "${result.search_string || 'pattern'}" first appeared in commit ${first.sha} by ${first.author}`,
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
