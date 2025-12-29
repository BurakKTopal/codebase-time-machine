import { MCPClient } from './mcpClient';
import { FactStore } from './factStore';
import {
    AgentConfig,
    ProgressUpdate,
    ProgressCallback,
    InvestigationResult,
    AgentPhase
} from './types';
import { getSynthesisThreshold, CORE_TOOLS } from './constants';
import {
    createProvider,
    ILLMProvider,
    LLMTool,
    LLMContentBlock
} from './providers';

// Re-export types for backward compatibility
export type { AgentConfig, ProgressUpdate, ProgressCallback, InvestigationResult };

/**
 * CTMAgent - Orchestrates code investigation using AI and MCP tools.
 *
 * Architecture:
 * - Uses FactStore for token-efficient state management
 * - State-based prompts rebuilt each iteration (not accumulated messages)
 * - Tool outputs are extracted into facts, then discarded
 * - Only CORE_TOOLS subset is sent to reduce schema size
 * - Provider-agnostic: works with Anthropic, OpenAI, Gemini
 */
export class CTMAgent {
    private provider: ILLMProvider;
    private mcpClient: MCPClient;
    private config: AgentConfig;
    private factStore: FactStore;
    private progressCallback?: ProgressCallback;
    private systemPrompt: string = '';
    private allTools: LLMTool[] = [];  // Cached tools
    private toolResultCache: Map<string, any> = new Map();  // Cache tool results

    constructor(mcpClient: MCPClient, config: AgentConfig) {
        this.provider = createProvider(config.provider, { apiKey: config.apiKey });
        this.mcpClient = mcpClient;
        this.config = config;
        this.factStore = new FactStore(config.apiKey);
        this.loadSystemPrompt();
    }

    private loadSystemPrompt(): void {
        const fs = require('fs');
        const path = require('path');
        const systemPromptPath = path.join(__dirname, 'SYSTEM_PROMPT.md');
        try {
            let prompt = fs.readFileSync(systemPromptPath, 'utf-8');

            // Inject current date so the agent knows what year it is
            const today = new Date();
            const dateStr = today.toISOString().split('T')[0]; // YYYY-MM-DD
            prompt += `\n\n---\n\n**Current Date:** ${dateStr}\n`;

            this.systemPrompt = prompt;
            console.log(`[CTM Agent] Loaded system prompt: ${this.systemPrompt.length} chars`);
        } catch (error) {
            console.error('[CTM Agent] Could not load SYSTEM_PROMPT.md:', error);
            this.systemPrompt = 'You are investigating code. Use get_local_line_context to start.';
        }
    }

    setProgressCallback(callback: ProgressCallback): void {
        this.progressCallback = callback;
    }

    private reportProgress(update: ProgressUpdate): void {
        if (this.progressCallback) {
            this.progressCallback(update);
        }
    }

    /**
     * Get tools - defaults to CORE_TOOLS for efficiency
     */
    private async getToolsForRequest(useAllTools: boolean = false): Promise<LLMTool[]> {
        // Load all tools once
        if (this.allTools.length === 0) {
            const mcpTools = await this.mcpClient.listTools();
            this.allTools = mcpTools.map(tool => ({
                name: tool.name,
                description: tool.description || `MCP tool: ${tool.name}`,
                inputSchema: tool.inputSchema as Record<string, unknown>
            }));
            console.log(`[CTM Agent] Loaded ${this.allTools.length} total tools`);
        }

        if (useAllTools) {
            // Use ALL tools (for comparison/debugging)
            console.log(`[CTM Agent] Using ALL ${this.allTools.length} tools`);
            return this.allTools;
        } else {
            // Filter to core tools only - MUCH smaller schema
            const coreTools = this.allTools.filter(t => CORE_TOOLS.includes(t.name));
            console.log(`[CTM Agent] Using ${coreTools.length} CORE tools (saving ${this.allTools.length - coreTools.length} tool schemas)`);
            return coreTools;
        }
    }

    /**
     * Build state-based prompt from current investigation state.
     */
    private buildStatePrompt(phase: AgentPhase, toolCallCount: number): string {
        const facts = this.factStore.getFactsSummary();
        const toolsCalled = this.factStore.getToolsCalled();

        if (phase === 'synthesize') {
            // Get tiered summary for answer-first approach
            const tieredSummary = this.factStore.getTieredSummary();

            // Include verbatim evidence during synthesis for precision answers
            const evidence = this.factStore.getEvidenceSummary();
            const evidenceSection = evidence ? `\n### Verbatim Evidence\n${evidence}\n` : '';

            // Check if code has multiple sections from different commits
            const hasCodeSections = facts.includes('CODE SECTIONS BREAKDOWN');
            const sectionCount = (facts.match(/Section \d+ \(lines/g) || []).length;
            const hasBlameWarning = facts.includes('LAST TOUCH') || facts.includes('LAST TOUCHED');

            const multiSectionInstructions = hasCodeSections ? `
**IMPORTANT: The selected code has ${sectionCount} distinct sections from different commits.**
The "CODE SECTIONS BREAKDOWN" above shows which lines were LAST TOUCHED by which commit.

⚠️ **CRITICAL DISTINCTION:**
- The commits shown are "LAST TOUCH" commits - they may have just MOVED or REFORMATTED the code
- For the TRUE ORIGIN of each section, you may need to use \`pickaxe_search\` with distinctive code strings
- Example: A TODO comment by "Oliveira" might show blame to a 2025 refactor commit, but pickaxe_search reveals it was actually written in 2023

**Your response MUST:**
1. Explain EACH section separately with its line range (e.g., "Lines 227-228...")
2. Clarify if the blame commit is the origin OR if you found an earlier origin via pickaxe
3. Include clickable hyperlinks for EVERY commit/PR/issue you mention
` : (hasBlameWarning ? `
⚠️ **Note:** The blame commit shown is the "LAST TOUCH" commit. If it says "refactor", "cleanup", or similar, use \`pickaxe_search\` to find the TRUE origin.
` : '');

            // Build suggested TL;DR section if available (compact, not duplicated in facts)
            const tldrSection = tieredSummary.tldr ? `
### 💡 Suggested TL;DR
${tieredSummary.tldr}
` : '';

            return `## Synthesize Your Findings

**LEAD WITH THE ANSWER, NOT THE ARCHAEOLOGY.**

**File:** ${this.config.filePath}
**Lines:** ${this.config.lineStart}-${this.config.lineEnd}

### Selected Code
\`\`\`
${this.config.selectedText}
\`\`\`
${tldrSection}
### Facts
${facts}
${evidenceSection}
### Tools Called
${toolsCalled.join(', ')}
${multiSectionInstructions}
Now write a clear, comprehensive explanation of WHY this code exists.

**START WITH A TL;DR (1-2 sentences answering "why does this code exist?")**
${tieredSummary.tldr ? `Use the suggested TL;DR above if accurate, or improve it.` : 'Write a clear conclusion first, then provide supporting evidence.'}

**MANDATORY - HYPERLINKS REQUIRED:**
Every commit SHA, PR number, and issue number MUST be a clickable hyperlink. Copy links from facts.

**Structure your answer with:**
1. **TL;DR** - One or two sentences answering "why does this code exist?"
2. **Origin** - When and by whom? Include clickable [commit](url) links.
3. **Context** - What [PR #N](url) or [Issue #N](url) led to this?
4. **Recommendation** - Should it be changed? (optional)

DO NOT call any more tools. Write your final answer now.`;
        }

        // Investigation phase
        // Check if we have blame results that might need origin verification
        const needsOriginVerification = facts.includes('LAST TOUCH') && !facts.includes('ORIGIN');
        const hasRefactorCommit = facts.toLowerCase().includes('refactor') ||
                                   facts.toLowerCase().includes('cleanup') ||
                                   facts.toLowerCase().includes('standardize');

        const originHint = needsOriginVerification && hasRefactorCommit ? `
⚠️ **IMPORTANT:** The blame commits show "refactor/cleanup" messages. These are likely NOT the true origin.
Use \`pickaxe_search\` with a distinctive code string to find when the code was actually introduced.
` : '';

        return `## Investigation Task

Investigate this code:
- **Repository:** ${this.config.owner}/${this.config.repo}
- **File:** ${this.config.filePath}
- **Lines:** ${this.config.lineStart}-${this.config.lineEnd}
- **Branch:** ${this.config.branch || 'HEAD'}
- **Local Path:** ${this.config.repoPath}

### Selected Code
\`\`\`
${this.config.selectedText}
\`\`\`

### Known Facts
${facts || 'No facts gathered yet. Start by calling get_local_line_context.'}
${originHint}
### Tools Already Called
${toolsCalled.length > 0 ? toolsCalled.join(', ') : 'None yet'}

### Remaining Tool Calls
${this.config.maxToolCalls - toolCallCount} calls remaining before synthesis.

${this.factStore.hasEnoughContext()
    ? '**You have enough context. Consider synthesizing now or getting more details.**'
    : '**Missing context. Continue investigating.**'}

Call a tool to gather more facts, or write your final synthesis if you have enough.`;
    }

    /**
     * Main investigation loop.
     */
    async investigate(): Promise<InvestigationResult> {
        console.log('[CTM Agent] ═══════════════════════════════════════════════════');
        console.log('[CTM Agent] Starting investigation');
        console.log('[CTM Agent] ═══════════════════════════════════════════════════');
        console.log('[CTM Agent] File:', this.config.filePath);
        console.log('[CTM Agent] Lines:', this.config.lineStart, '-', this.config.lineEnd);

        // Get core tools only
        const tools = await this.getToolsForRequest();

        this.reportProgress({
            phase: 'investigate',
            toolCallCount: 0,
            maxToolCalls: this.config.maxToolCalls,
            message: 'Starting investigation...',
            percentage: 5
        });

        let phase: AgentPhase = 'investigate';
        let toolCallCount = 0;
        let iteration = 0;
        let finalResponse = '';
        let totalInputTokens = 0;
        let totalOutputTokens = 0;
        let completionReason: 'natural' | 'limit_reached' | 'threshold_reached' = 'natural';

        // Main loop - each iteration is a FRESH prompt based on current state
        while (true) {
            iteration++;

            // Phase transition check
            if (phase === 'investigate' && toolCallCount >= getSynthesisThreshold(this.config.maxToolCalls)) {
                phase = 'synthesize';
                completionReason = 'threshold_reached';
                console.log(`[CTM Agent] PHASE TRANSITION: investigate → synthesize`);
                console.log(`[CTM Agent] Facts gathered: ${this.factStore.getFactCount()}`);

                this.reportProgress({
                    phase: 'synthesize',
                    toolCallCount,
                    maxToolCalls: this.config.maxToolCalls,
                    message: 'Synthesizing findings...',
                    percentage: 85
                });
            }

            // Build state-based prompt (NOT conversation history)
            const statePrompt = this.buildStatePrompt(phase, toolCallCount);
            const messages = [
                { role: 'user' as const, content: statePrompt }
            ];

            // Tools only in investigate phase
            const toolsToUse = phase === 'investigate' ? tools : [];

            console.log(`[CTM Agent] Iteration ${iteration} | Phase: ${phase} | Facts: ${this.factStore.getFactCount()} | Tool calls: ${toolCallCount}`);

            // Log prompt size
            const promptTokensEstimate = Math.ceil(statePrompt.length / 4);
            console.log(`[CTM Agent] State prompt: ~${promptTokensEstimate} tokens (${statePrompt.length} chars)`);

            // Make API call using provider abstraction
            // Use higher maxTokens for synthesis phase to avoid truncation
            const maxTokens = phase === 'synthesize' ? 8000 : 4000;
            const response = await this.provider.createMessage({
                model: this.config.model,
                maxTokens,
                systemPrompt: this.systemPrompt,
                tools: toolsToUse.length > 0 ? toolsToUse : undefined,
                messages: messages.map(m => ({ role: m.role as 'user' | 'assistant', content: m.content as string }))
            });

            totalInputTokens += response.usage.inputTokens;
            totalOutputTokens += response.usage.outputTokens;

            console.log(`[CTM Agent] Response: input=${response.usage.inputTokens}, output=${response.usage.outputTokens}, stop=${response.stopReason}`);

            const textContent = response.content.find((block: LLMContentBlock) => block.type === 'text');
            const toolUses = response.content.filter((block: LLMContentBlock) => block.type === 'tool_use');

            // SYNTHESIS PHASE: Get text response and finish
            if (phase === 'synthesize') {
                if (textContent && textContent.type === 'text') {
                    finalResponse = textContent.text;
                    console.log(`[CTM Agent] Synthesis complete: ${finalResponse.length} chars`);

                    this.reportProgress({
                        phase: 'complete',
                        toolCallCount,
                        maxToolCalls: this.config.maxToolCalls,
                        message: 'Analysis complete!',
                        percentage: 100
                    });
                    break;
                }

                // If it tried to use tools in synthesis, just ask again
                if (toolUses.length > 0) {
                    console.log(`[CTM Agent] Ignoring tool calls in synthesis phase`);
                    continue;
                }
            }

            // INVESTIGATE PHASE: Handle tool calls
            if (phase === 'investigate' && toolUses.length > 0) {
                for (const toolUse of toolUses) {
                    if (toolUse.type !== 'tool_use') continue;

                    toolCallCount++;
                    console.log(`[CTM Agent] Tool call ${toolCallCount}/${this.config.maxToolCalls}: ${toolUse.name}`);

                    this.reportProgress({
                        phase: 'investigate',
                        toolCallCount,
                        maxToolCalls: this.config.maxToolCalls,
                        currentTool: toolUse.name,
                        message: `Analyzing ${this.formatToolName(toolUse.name)}...`,
                        percentage: Math.min(80, 10 + (toolCallCount / this.config.maxToolCalls) * 70)
                    });

                    // Execute tool
                    const result = await this.executeTool(toolUse.name, toolUse.input);

                    // CRITICAL: Extract facts and DELETE the raw result
                    const confirmation = await this.factStore.extractAndStore(toolUse.name, result);
                    console.log(`[CTM Agent] ${confirmation}`);
                    console.log(`[CTM Agent] Total facts: ${this.factStore.getFactCount()}`);

                    // Check hard cap
                    if (toolCallCount >= this.config.maxToolCalls) {
                        console.log(`[CTM Agent] Hit this.config.maxToolCalls - forcing synthesis`);
                        phase = 'synthesize';
                        completionReason = 'limit_reached';
                        break;
                    }
                }

                // Continue loop - next iteration will rebuild state prompt with new facts
                continue;
            }

            // No tool calls in investigate phase = natural completion
            if (phase === 'investigate' && toolUses.length === 0) {
                if (textContent && textContent.type === 'text') {
                    finalResponse = textContent.text;
                    console.log(`[CTM Agent] Natural completion: ${finalResponse.length} chars`);

                    this.reportProgress({
                        phase: 'complete',
                        toolCallCount,
                        maxToolCalls: this.config.maxToolCalls,
                        message: 'Analysis complete!',
                        percentage: 100
                    });
                    break;
                }
            }

            // Safety
            if (iteration > 15) {
                console.error('[CTM Agent] ERROR: Too many iterations');
                finalResponse = 'Investigation exceeded maximum iterations.';
                break;
            }
        }

        // Summary
        console.log('\n[CTM Agent] ═══════════════════════════════════════════════════');
        console.log('[CTM Agent] INVESTIGATION SUMMARY');
        console.log('[CTM Agent] ═══════════════════════════════════════════════════');
        console.log(`[CTM Agent] Iterations: ${iteration}`);
        console.log(`[CTM Agent] Tool calls: ${toolCallCount}`);
        console.log(`[CTM Agent] Facts gathered: ${this.factStore.getFactCount()}`);
        console.log(`[CTM Agent] Total tokens: ${totalInputTokens + totalOutputTokens}`);
        console.log(`[CTM Agent]   - Input: ${totalInputTokens}`);
        console.log(`[CTM Agent]   - Output: ${totalOutputTokens}`);
        console.log(`[CTM Agent] Completion: ${completionReason}`);
        console.log('[CTM Agent] ═══════════════════════════════════════════════════');

        // Build rawContext from facts for UI display
        const rawContext = this.buildRawContextFromFacts();
        const contextQuality = this.assessContextQuality(rawContext);

        return {
            summary: finalResponse,
            rawContext,
            completionReason,
            contextQuality,
            toolCallsUsed: toolCallCount,
            toolsUsed: this.factStore.getToolsCalled(),
            tokensUsed: totalInputTokens + totalOutputTokens
        };
    }

    /**
     * Build rawContext from facts and evidence for UI display
     */
    private buildRawContextFromFacts(): any {
        const facts = Array.from(this.factStore['facts'].values());
        const evidence = Array.from(this.factStore['evidence'].values());
        const context: any = {
            file_path: this.config.filePath,
            line_start: this.config.lineStart,
            line_end: this.config.lineEnd
        };

        // Build evidence lookup for quick access
        const evidenceByType: Record<string, any[]> = {};
        for (const e of evidence) {
            if (!evidenceByType[e.type]) evidenceByType[e.type] = [];
            evidenceByType[e.type].push(e);
        }

        // Extract structured data from facts
        // Initialize blame_commits array for multi-line selections
        const blameCommits: any[] = [];

        for (const fact of facts) {
            if (fact.id.startsWith('blame_') && !fact.id.includes('multi_commit')) {
                // Parse fact text: "Blame commit [abc123](url): by Author on 2024-01-15 - "Message" [lines: 227, 228]"
                // Handle markdown links: [sha](url) or plain sha
                const shaMatch = fact.text.match(/commit \[?([a-f0-9]+)\]?(?:\([^)]+\))?:/i);
                const authorMatch = fact.text.match(/by ([^<\n]+?)(?:\s+on\s+|\s*<)/);
                const dateMatch = fact.text.match(/on (\d{4}-\d{2}-\d{2})/);
                const messageMatch = fact.text.match(/-\s*"([^"]+)"/);
                const linesMatch = fact.text.match(/\[lines:\s*([^\]]+)\]/);
                const urlMatch = fact.text.match(/\[([a-f0-9]+)\]\(([^)]+)\)/);

                // Get full SHA from evidence
                const shortSha = shaMatch?.[1];
                const blameEvidence = evidenceByType['sha']?.find(e => e.id.includes(shortSha || 'blame'));
                const authorEvidence = evidenceByType['author']?.find(e => e.id.includes(shortSha || 'blame'));
                const timestampEvidence = evidenceByType['timestamp']?.find(e => e.id.includes(shortSha || 'blame'));

                // Get SHA for URL construction
                const fullSha = blameEvidence?.verbatim || shaMatch?.[1] || null;

                // Construct html_url: from markdown link, or build from owner/repo
                let htmlUrl = urlMatch?.[2] || null;
                if (!htmlUrl && fullSha && this.config.owner && this.config.repo) {
                    htmlUrl = `https://github.com/${this.config.owner}/${this.config.repo}/commit/${fullSha}`;
                }

                const blameInfo = {
                    sha: fullSha,
                    author: authorEvidence?.verbatim || authorMatch?.[1]?.trim() || null,
                    date: timestampEvidence?.verbatim || dateMatch?.[1] || null,
                    message: messageMatch?.[1] || null,
                    html_url: htmlUrl,
                    lines: linesMatch?.[1]?.split(',').map((l: string) => parseInt(l.trim())) || null,
                    summary: fact.text
                };

                blameCommits.push(blameInfo);

                // Set primary blame_commit (first one = most lines)
                if (!context.blame_commit) {
                    context.blame_commit = blameInfo;
                }
            }
            if (fact.id.startsWith('pr_')) {
                // Skip body/discussion facts for initial PR parsing
                if (fact.id.includes('_body') || fact.id.includes('_discussion')) {
                    // Handle PR body from separate fact
                    if (fact.id.includes('_body') && context.pull_request) {
                        const bodyMatch = fact.text.match(/description:\s*(.+)/);
                        if (bodyMatch) {
                            context.pull_request.body = bodyMatch[1];
                        }
                    }
                    continue;
                }

                // Extract PR number - handle both markdown links [PR #123](url) and plain PR #123
                const prNumMatch = fact.text.match(/PR #(\d+)/);
                const prNumber = prNumMatch ? parseInt(prNumMatch[1]) : null;
                if (!prNumber) continue;

                // Get evidence
                const urlEvidence = evidenceByType['url']?.find(e => e.id.includes(`pr_${prNumber}`));
                const authorEvidence = evidenceByType['author']?.find(e => e.id.includes(`pr_${prNumber}`));
                const timestampEvidence = evidenceByType['timestamp']?.find(e => e.id.includes(`pr_${prNumber}`));

                // Parse title - handle both formats:
                // 1. Markdown: [PR #123](url): "Title" by Author (state)
                // 2. Plain: PR #123: "Title" by Author (state)
                // 3. Code section: [PR #123](url): "Commit message" by Author (from code section lines X-Y)
                const titleMatch = fact.text.match(/PR #\d+\]?\)?:\s*"([^"]+)"/);

                // Check if this is from a code section (has different format)
                const isFromCodeSection = fact.text.includes('from code section');

                // For state: match (merged), (open), (closed) but NOT (from code section...)
                // State appears right before " by Author" or at end, as a single word in parens
                const stateMatch = isFromCodeSection ? null : fact.text.match(/\((merged|open|closed)\)/i);

                // For author: match the LAST "by Author" pattern (after the title quotes)
                // Use a more specific pattern: " by AuthorName (" or " by AuthorName$"
                // For code sections: pattern is `" by Author (from code section`
                const authorMatch = fact.text.match(/" by ([^(]+?)\s*\(/);

                // Extract URL from markdown link if present
                const urlMatch = fact.text.match(/\[PR #\d+\]\(([^)]+)\)/);
                const prUrl = urlMatch?.[1] || urlEvidence?.verbatim || null;

                const parsedPR = {
                    number: prNumber,
                    title: titleMatch?.[1] || null,
                    author: authorEvidence?.verbatim || authorMatch?.[1]?.trim() || null,
                    state: stateMatch?.[1] || null,
                    html_url: prUrl,
                    created_at: timestampEvidence?.verbatim || null,
                    merged_at: null,
                    body: null,
                    summary: fact.text
                };

                // If state is merged, use created_at as merged_at approximation
                if (parsedPR.state === 'merged') {
                    parsedPR.merged_at = parsedPR.created_at;
                }

                // Prefer PRs with actual state info (from get_pr) over code_section PRs
                const hasCompleteInfo = parsedPR.state && !isFromCodeSection;

                if (!context.pull_request) {
                    // No PR yet, use this one
                    context.pull_request = parsedPR;
                } else if (hasCompleteInfo && !context.pull_request.state) {
                    // This PR has more complete info, replace
                    context.pull_request = parsedPR;
                }
            }
            if (fact.id.startsWith('issue_')) {
                if (!context.linked_issues) context.linked_issues = [];

                // Skip body facts - we'll handle them separately
                if (fact.id.includes('_body') || fact.id.includes('_desc')) {
                    continue;
                }

                const match = fact.text.match(/Issue #(\d+)/);
                const issueNumber = match ? parseInt(match[1]) : null;

                // Get URL from evidence
                const urlEvidence = evidenceByType['url']?.find(e => e.id.includes(`issue_${issueNumber}`));
                const authorEvidence = evidenceByType['author']?.find(e => e.id.includes(`issue_${issueNumber}`));

                // Parse from fact text: 'Issue #123: "Title" by Author (state)'
                const titleMatch = fact.text.match(/Issue #\d+\]?\)?:\s*"([^"]+)"/);
                const authorMatch = fact.text.match(/" by ([^(]+?)\s*\(/);
                const stateMatch = fact.text.match(/\((open|closed)\)/i);

                // Extract URL from markdown link if present
                const urlMatch = fact.text.match(/\[Issue #\d+\]\(([^)]+)\)/);

                context.linked_issues.push({
                    number: issueNumber,
                    title: titleMatch?.[1] || null,
                    author: authorEvidence?.verbatim || authorMatch?.[1]?.trim() || null,
                    state: stateMatch?.[1] || null,
                    html_url: urlMatch?.[1] || urlEvidence?.verbatim || null,
                    body: null, // Will be set from _body fact if it exists
                    summary: fact.text
                });
            }
            if (fact.id.startsWith('origin_')) {
                // Parse origin fact: "ORIGIN commit [abc123](url): Code first added by Author on 2024-01-15"
                // Handle markdown links
                const shaMatch = fact.text.match(/commit \[?([a-f0-9]+)\]?(?:\([^)]+\))?:/i);
                const authorMatch = fact.text.match(/by ([^<\n]+?)(?:\s+on\s+|\s*$)/);
                const dateMatch = fact.text.match(/on (\d{4}-\d{2}-\d{2})/);
                const urlMatch = fact.text.match(/\[([a-f0-9]+)\]\(([^)]+)\)/);

                context.origin = {
                    sha: shaMatch?.[1] || null,
                    author: authorMatch?.[1]?.trim() || null,
                    date: dateMatch?.[1] || null,
                    html_url: urlMatch?.[2] || null,
                    summary: fact.text
                };
            }
        }

        // Add blame_commits array if multiple commits found
        if (blameCommits.length > 1) {
            context.blame_commits = blameCommits;
        }

        return context;
    }

    private assessContextQuality(context: any): 'high' | 'medium' | 'low' {
        let score = 0;
        if (context.blame_commit) score += 1;
        if (context.pull_request) score += 2;
        if (context.linked_issues?.length > 0) score += 2;
        if (context.origin) score += 1;

        if (score >= 5) return 'high';
        if (score >= 3) return 'medium';
        return 'low';
    }

    /**
     * Ask a follow-up question - WITH tool support and optional streaming
     */
    async askFollowUp(
        question: string,
        previousSummary: string,
        onStream?: (text: string) => void
    ): Promise<string> {
        console.log('[CTM Agent] Processing follow-up question:', question);
        console.log('[CTM Agent] Current facts:', this.factStore.getFactCount());

        // Get tools for follow-up (same core tools)
        const tools = await this.getToolsForRequest();

        // Track tool calls made in this follow-up to prevent loops
        const toolCallsMade: string[] = [];

        // Helper to build the prompt with current facts
        const buildFollowUpPrompt = (): string => {
            const evidence = this.factStore.getEvidenceSummary();
            const evidenceSection = evidence ? `\n**Verbatim Evidence:**\n${evidence}\n` : '';

            // Show what tools have been called to prevent repeating
            const toolCallsSection = toolCallsMade.length > 0
                ? `\n**Tools Already Called (do NOT repeat these):**\n${toolCallsMade.map(t => `- ${t}`).join('\n')}\n`
                : '';

            return `## Follow-up Question

**File:** ${this.config.filePath}
**Lines:** ${this.config.lineStart}-${this.config.lineEnd}
**Repository:** ${this.config.owner}/${this.config.repo}
**Local Path:** ${this.config.repoPath}

**Selected Code:**
\`\`\`
${this.config.selectedText}
\`\`\`

**Known Facts:**
${this.factStore.getFactsSummary()}
${evidenceSection}${toolCallsSection}
**Previous Analysis:**
${previousSummary}

**User Question:**
${question}

If you can answer from the known facts, selected code, or verbatim evidence (like emails), do so.
If you need more information that isn't in the facts, USE A TOOL to find it (but don't repeat tools you already called).
For example, use pickaxe_search to find when specific code/text was added or removed.
If the information you need is not available, say so - don't keep searching.`;
        };

        let toolCallCount = 0;
        const MAX_FOLLOWUP_TOOLS = 5;  // Increased to allow more investigation
        let finalResponse = '';

        // Loop to handle potential tool calls
        while (toolCallCount < MAX_FOLLOWUP_TOOLS) {
            // CRITICAL: Rebuild prompt each iteration with updated facts
            const prompt = buildFollowUpPrompt();

            const requestConfig = {
                model: this.config.model,
                maxTokens: 2000,
                systemPrompt: this.systemPrompt,
                tools: tools,
                messages: [{ role: 'user' as const, content: prompt }]
            };

            // Use streaming if available and this might be the final response
            // We first do a non-streaming call to check for tool usage
            const response = await this.provider.createMessage(requestConfig);

            console.log(`[CTM Agent] Follow-up response: input=${response.usage.inputTokens}, output=${response.usage.outputTokens}, stop=${response.stopReason}`);

            const textContent = response.content.find((block: LLMContentBlock) => block.type === 'text');
            const toolUses = response.content.filter((block: LLMContentBlock) => block.type === 'tool_use');

            // If no tool calls, we have our answer
            if (toolUses.length === 0) {
                if (textContent && textContent.type === 'text') {
                    finalResponse = textContent.text;
                    // Stream the complete response if callback provided
                    if (onStream) {
                        onStream(finalResponse);
                    }
                }
                break;
            }

            // Handle tool calls
            let newCallsThisIteration = 0;
            for (const toolUse of toolUses) {
                if (toolUse.type !== 'tool_use') continue;

                // Create a signature for this tool call to detect duplicates
                const toolSignature = `${toolUse.name}(${JSON.stringify(toolUse.input)})`;

                // Skip if we already made this exact call
                if (toolCallsMade.includes(toolSignature)) {
                    console.log(`[CTM Agent] SKIPPING duplicate tool call: ${toolUse.name}`);
                    continue;
                }

                toolCallCount++;
                newCallsThisIteration++;
                toolCallsMade.push(toolSignature);
                console.log(`[CTM Agent] Follow-up tool call ${toolCallCount}/${MAX_FOLLOWUP_TOOLS}: ${toolUse.name}`);

                this.reportProgress({
                    phase: 'investigate',
                    toolCallCount,
                    maxToolCalls: MAX_FOLLOWUP_TOOLS,
                    currentTool: toolUse.name,
                    message: `Checking ${this.formatToolName(toolUse.name)}...`,
                    percentage: 30 + (toolCallCount / MAX_FOLLOWUP_TOOLS) * 50
                });

                // Execute tool
                const result = await this.executeTool(toolUse.name, toolUse.input);

                // Extract facts - next iteration will see these in the rebuilt prompt
                const confirmation = await this.factStore.extractAndStore(toolUse.name, result);
                console.log(`[CTM Agent] ${confirmation}`);
            }

            // If all tool calls were duplicates, break the loop to avoid infinite loop
            if (toolUses.length > 0 && newCallsThisIteration === 0) {
                console.log(`[CTM Agent] All tool calls were duplicates - forcing synthesis`);
                break;
            }

            // Continue loop - prompt will be rebuilt with new facts
        }

        // If we hit tool limit without a response, synthesize one (with streaming if available)
        if (!finalResponse) {
            // Include verbatim evidence for precision answers
            const evidence = this.factStore.getEvidenceSummary();
            const evidenceSection = evidence ? `\n\nVerbatim Evidence:\n${evidence}` : '';

            const synthConfig = {
                model: this.config.model,
                maxTokens: 2000,
                messages: [{
                    role: 'user' as const,
                    content: `Based on these facts, answer the question: "${question}"\n\nFacts:\n${this.factStore.getFactsSummary()}${evidenceSection}`
                }]
            };

            if (onStream) {
                // Use streaming for synthesis
                let streamedText = '';
                await this.provider.createMessageStream(synthConfig, (chunk) => {
                    if (chunk.type === 'text_delta') {
                        streamedText += chunk.text;
                        onStream(chunk.text);
                    }
                });
                finalResponse = streamedText || 'Unable to find additional information.';
            } else {
                // Non-streaming fallback
                const synthResponse = await this.provider.createMessage(synthConfig);
                const textContent = synthResponse.content.find((block: LLMContentBlock) => block.type === 'text');
                finalResponse = textContent && textContent.type === 'text' ? textContent.text : 'Unable to find additional information.';
            }
        }

        console.log(`[CTM Agent] Follow-up complete. Facts: ${this.factStore.getFactCount()}`);
        return finalResponse;
    }

    private formatToolName(toolName: string): string {
        const labels: Record<string, string> = {
            'get_local_line_context': 'line context',
            'get_line_context': 'line context',
            'get_commit': 'commit details',
            'get_github_commit': 'commit details',
            'get_pr': 'pull request',
            'get_issue': 'issue',
            'search_prs_for_commit': 'PR search',
            'get_github_file_history': 'file history',
            'trace_file_history': 'file history',
            'get_commit_diff': 'commit diff',
            'pickaxe_search': 'code history search',
            'get_code_owners': 'code owners',
            'explain_file': 'file overview',
            'get_github_commits_batch': 'commit batch'
        };
        return labels[toolName] || toolName.replace(/_/g, ' ');
    }

    private async executeTool(toolName: string, input: any): Promise<any> {
        // Auto-translate parameters for local tools
        const translatedInput = { ...input };

        if (toolName.startsWith('get_local_') || toolName === 'trace_file_history' ||
            toolName === 'get_commit' || toolName === 'get_commit_diff' ||
            toolName === 'blame_with_context' || toolName === 'get_file_at_commit' ||
            toolName === 'pickaxe_search' || toolName === 'get_file_symbols' ||
            toolName === 'trace_symbol_history' || toolName === 'explain_commit') {
            if (!translatedInput.repo_path && this.config.repoPath) {
                translatedInput.repo_path = this.config.repoPath;
            }
        }

        // Generate cache key from tool name and input
        const cacheKey = `${toolName}:${JSON.stringify(translatedInput)}`;

        // Check cache first
        if (this.toolResultCache.has(cacheKey)) {
            console.log(`[CTM Agent] CACHE HIT for ${toolName}`);
            return this.toolResultCache.get(cacheKey);
        }

        console.log(`[CTM Agent] Executing ${toolName}`);
        const result = await this.mcpClient.callTool(toolName, translatedInput);

        // Cache the result (only if successful)
        if (result && !result.error) {
            this.toolResultCache.set(cacheKey, result);
            console.log(`[CTM Agent] Cached result for ${toolName} (cache size: ${this.toolResultCache.size})`);
        }

        console.groupCollapsed(`[CTM Agent] Tool result for ${toolName} (click to expand)`);
        console.log(JSON.stringify(result, null, 2));
        console.groupEnd();

        return result;
    }
}
