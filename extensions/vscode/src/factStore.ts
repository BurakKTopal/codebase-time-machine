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
 * Investigation state - replaces conversation history.
 * This is what gets sent to the model instead of accumulated messages.
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
 * FactStore: The Claude Code secret sauce.
 *
 * Instead of keeping raw tool outputs in conversation history (3000 tokens each),
 * we extract durable facts (60 tokens total) and DELETE the evidence.
 *
 * This reduces token usage by 90%+.
 */
export class FactStore {
    private facts: Map<string, Fact> = new Map();
    private toolsCalled: string[] = [];
    private anthropic: Anthropic;

    constructor(apiKey: string) {
        this.anthropic = new Anthropic({ apiKey, dangerouslyAllowBrowser: true });
    }

    /**
     * Extract facts from a tool result and store them.
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

        // Store facts (deduplicated by ID)
        facts.forEach(f => this.facts.set(f.id, f));

        console.log(`[FactStore] Extracted ${facts.length} facts from ${toolName}`);
        console.log(`[FactStore] Total facts: ${this.facts.size}`);

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
            // Blame commit
            if (result.blame_commit) {
                const bc = result.blame_commit;
                facts.push({
                    id: `blame_${bc.sha?.substring(0, 8)}`,
                    text: `Last touched by ${bc.author} on ${bc.date?.substring(0, 10)}: "${bc.message?.split('\n')[0]?.substring(0, 80)}"`,
                    source: toolName,
                    category: 'commit'
                });
            }

            // PR
            if (result.pull_request) {
                const pr = result.pull_request;
                facts.push({
                    id: `pr_${pr.number}`,
                    text: `PR #${pr.number}: "${pr.title}" by ${pr.author}`,
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
                    facts.push({
                        id: `issue_${issue.number}`,
                        text: `Issue #${issue.number}: "${issue.title}"`,
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

            // Historical commits (when code was introduced)
            if (result.historical_commits && result.historical_commits.length > 0) {
                const firstCommit = result.historical_commits[result.historical_commits.length - 1];
                if (firstCommit) {
                    facts.push({
                        id: `origin_${firstCommit.sha?.substring(0, 8)}`,
                        text: `Code originally added by ${firstCommit.author} on ${firstCommit.date?.substring(0, 10)}: "${firstCommit.message?.split('\n')[0]?.substring(0, 80)}"`,
                        source: toolName,
                        category: 'commit'
                    });
                }
            }
        }

        // Handle get_pr
        if (toolName === 'get_pr') {
            facts.push({
                id: `pr_${result.number}`,
                text: `PR #${result.number}: "${result.title}" by ${result.author} (${result.state})`,
                source: toolName,
                category: 'pr'
            });
            if (result.body) {
                facts.push({
                    id: `pr_${result.number}_body`,
                    text: `PR #${result.number} description: ${result.body.substring(0, 300)}...`,
                    source: toolName,
                    category: 'pr'
                });
            }
            if (result.comments && result.comments.length > 0) {
                const keyComment = result.comments.find((c: any) => c.body && c.body.length > 50);
                if (keyComment) {
                    facts.push({
                        id: `pr_${result.number}_discussion`,
                        text: `PR discussion: @${keyComment.author}: "${keyComment.body.substring(0, 150)}..."`,
                        source: toolName,
                        category: 'pr'
                    });
                }
            }
        }

        // Handle get_issue
        if (toolName === 'get_issue') {
            facts.push({
                id: `issue_${result.number}`,
                text: `Issue #${result.number}: "${result.title}" by ${result.author} (${result.state})`,
                source: toolName,
                category: 'issue'
            });
            if (result.body) {
                facts.push({
                    id: `issue_${result.number}_body`,
                    text: `Issue #${result.number} problem: ${result.body.substring(0, 300)}...`,
                    source: toolName,
                    category: 'issue'
                });
            }
        }

        // Handle get_commit / get_github_commit
        if (toolName === 'get_commit' || toolName === 'get_github_commit') {
            const commit = result.commit || result;
            facts.push({
                id: `commit_${commit.sha?.substring(0, 8)}`,
                text: `Commit ${commit.sha?.substring(0, 8)} by ${commit.author} on ${commit.date?.substring(0, 10)}: "${commit.message?.split('\n')[0]}"`,
                source: toolName,
                category: 'commit'
            });
        }

        // Handle search_prs_for_commit
        if (toolName === 'search_prs_for_commit' && result.items && result.items.length > 0) {
            const pr = result.items[0];
            facts.push({
                id: `pr_${pr.number}`,
                text: `Found PR #${pr.number}: "${pr.title}" by ${pr.author}`,
                source: toolName,
                category: 'pr'
            });
        }

        // Handle file history
        if ((toolName === 'get_github_file_history' || toolName === 'trace_file_history') && result.commits) {
            facts.push({
                id: 'file_history',
                text: `File has ${result.commits.length} commits. Recent: ${result.commits.slice(0, 3).map((c: any) => c.message?.split('\n')[0]?.substring(0, 40)).join('; ')}`,
                source: toolName,
                category: 'commit'
            });
        }

        return facts;
    }

    /**
     * Get all facts as a compact string for the model.
     * This is what replaces the raw tool outputs in conversation.
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
        if (factsByCategory.has('other')) {
            lines.push('**Other:**');
            factsByCategory.get('other')!.forEach(f => lines.push(`- ${f.text}`));
        }

        return lines.join('\n');
    }

    /**
     * Get the current investigation state.
     * This is what gets sent to the model instead of conversation history.
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
     * Clear all facts (for new investigation).
     */
    clear(): void {
        this.facts.clear();
        this.toolsCalled = [];
    }
}
