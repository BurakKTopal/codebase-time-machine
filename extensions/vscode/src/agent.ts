import Anthropic from '@anthropic-ai/sdk';
import { MCPClient } from './mcpClient';
import { FactStore } from './factStore';

export interface AgentConfig {
    apiKey: string;
    owner: string;
    repo: string;
    repoPath: string;
    filePath: string;
    lineStart: number;
    lineEnd: number;
    branch?: string;
}

// Progress update for UI feedback
export interface ProgressUpdate {
    phase: 'investigate' | 'synthesize' | 'complete';
    toolCallCount: number;
    maxToolCalls: number;
    currentTool?: string;
    message: string;
    percentage: number;
}

export type ProgressCallback = (update: ProgressUpdate) => void;

// Export type for use in other modules
export type { AgentConfig as CTMAgentConfig };

// Investigation result with metadata for continue functionality
export interface InvestigationResult {
    summary: string;
    rawContext: any;
    completionReason: 'natural' | 'limit_reached' | 'threshold_reached';
    contextQuality: 'high' | 'medium' | 'low';
    canContinue: boolean;
    toolCallsUsed: number;
    toolsUsed: string[];
    tokensUsed: number;
}

// State preserved for continuation
export interface InvestigationState {
    summary: string;
    toolsUsed: string[];
    rawContext: any;
    toolCallsUsed: number;
    tokensUsed: number;
}

// Configuration - LOWER limits since we're more efficient now
const MAX_TOOL_CALLS = 8;  // Reduced from 12 - we need fewer calls with better context
const SYNTHESIS_THRESHOLD = 6;  // Reduced from 8

// Core tools - only send these (not all 35)
const CORE_TOOLS = [
    'get_local_line_context',  // Primary tool - gets everything
    'get_commit',
    'get_pr',
    'get_issue',
    'search_prs_for_commit',
    'get_github_file_history',
    'trace_file_history',
    'get_commit_diff'
];

type AgentPhase = 'investigate' | 'synthesize';

/**
 * CTMAgent - Claude Code Architecture
 *
 * Key differences from before:
 * 1. Uses FactStore instead of conversation history
 * 2. State-based prompts instead of accumulated messages
 * 3. Tool outputs are extracted → deleted (not kept)
 * 4. Only CORE_TOOLS are sent (not all 35)
 */
export class CTMAgent {
    private anthropic: Anthropic;
    private mcpClient: MCPClient;
    private config: AgentConfig;
    private factStore: FactStore;
    private progressCallback?: ProgressCallback;
    private systemPrompt: string = '';
    private allTools: Anthropic.Tool[] = [];  // Cached tools

    constructor(mcpClient: MCPClient, config: AgentConfig) {
        this.anthropic = new Anthropic({ apiKey: config.apiKey, dangerouslyAllowBrowser: true });
        this.mcpClient = mcpClient;
        this.config = config;
        this.factStore = new FactStore(config.apiKey);
        this.loadSystemPrompt();
    }

    private loadSystemPrompt(): void {
        const fs = require('fs');
        const path = require('path');
        const claudeMdPath = path.join(__dirname, 'CLAUDE.md');
        try {
            this.systemPrompt = fs.readFileSync(claudeMdPath, 'utf-8');
            console.log(`[CTM Agent] Loaded system prompt: ${this.systemPrompt.length} chars`);
        } catch (error) {
            console.error('[CTM Agent] Could not load CLAUDE.md:', error);
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
     * Get tools - only CORE_TOOLS, and track if we've sent them
     */
    private async getToolsForRequest(): Promise<Anthropic.Tool[]> {
        // Load all tools once
        if (this.allTools.length === 0) {
            const mcpTools = await this.mcpClient.listTools();
            this.allTools = mcpTools.map(tool => ({
                name: tool.name,
                description: tool.description || `MCP tool: ${tool.name}`,
                input_schema: tool.inputSchema as Anthropic.Tool.InputSchema
            }));
            console.log(`[CTM Agent] Loaded ${this.allTools.length} tools, filtering to ${CORE_TOOLS.length} core tools`);
        }

        // Filter to core tools only
        const coreTools = this.allTools.filter(t => CORE_TOOLS.includes(t.name));
        console.log(`[CTM Agent] Using ${coreTools.length} core tools (not ${this.allTools.length})`);

        return coreTools;
    }

    /**
     * Build state-based prompt - this replaces conversation history
     */
    private buildStatePrompt(phase: AgentPhase, toolCallCount: number): string {
        const facts = this.factStore.getFactsSummary();
        const toolsCalled = this.factStore.getToolsCalled();

        if (phase === 'synthesize') {
            return `## Synthesize Your Findings

You have gathered the following facts about this code:

**File:** ${this.config.filePath}
**Lines:** ${this.config.lineStart}-${this.config.lineEnd}

### Known Facts
${facts}

### Tools Called
${toolsCalled.join(', ')}

Now write a clear, comprehensive explanation of WHY this code exists.
Structure your answer with:
1. **Origin** - When and by whom was this code added?
2. **Purpose** - What problem does it solve?
3. **Context** - What PR/issue led to this?
4. **Recommendation** - Should it be changed?

DO NOT call any more tools. Write your final answer now.`;
        }

        // Investigation phase
        return `## Investigation Task

Investigate this code:
- **Repository:** ${this.config.owner}/${this.config.repo}
- **File:** ${this.config.filePath}
- **Lines:** ${this.config.lineStart}-${this.config.lineEnd}
- **Branch:** ${this.config.branch || 'HEAD'}
- **Local Path:** ${this.config.repoPath}

### Known Facts
${facts || 'No facts gathered yet. Start by calling get_local_line_context.'}

### Tools Already Called
${toolsCalled.length > 0 ? toolsCalled.join(', ') : 'None yet'}

### Remaining Tool Calls
${MAX_TOOL_CALLS - toolCallCount} calls remaining before synthesis.

${this.factStore.hasEnoughContext()
    ? '**You have enough context. Consider synthesizing now or getting more details.**'
    : '**Missing context. Continue investigating.**'}

Call a tool to gather more facts, or write your final synthesis if you have enough.`;
    }

    /**
     * Main investigation loop - Claude Code architecture
     */
    async investigate(): Promise<InvestigationResult> {
        console.log('[CTM Agent] ═══════════════════════════════════════════════════');
        console.log('[CTM Agent] Starting investigation (Claude Code Architecture)');
        console.log('[CTM Agent] ═══════════════════════════════════════════════════');
        console.log('[CTM Agent] File:', this.config.filePath);
        console.log('[CTM Agent] Lines:', this.config.lineStart, '-', this.config.lineEnd);

        // Get core tools only
        const tools = await this.getToolsForRequest();

        this.reportProgress({
            phase: 'investigate',
            toolCallCount: 0,
            maxToolCalls: MAX_TOOL_CALLS,
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
            if (phase === 'investigate' && toolCallCount >= SYNTHESIS_THRESHOLD) {
                phase = 'synthesize';
                completionReason = 'threshold_reached';
                console.log(`[CTM Agent] PHASE TRANSITION: investigate → synthesize`);
                console.log(`[CTM Agent] Facts gathered: ${this.factStore.getFactCount()}`);

                this.reportProgress({
                    phase: 'synthesize',
                    toolCallCount,
                    maxToolCalls: MAX_TOOL_CALLS,
                    message: 'Synthesizing findings...',
                    percentage: 85
                });
            }

            // Build state-based prompt (NOT conversation history)
            const statePrompt = this.buildStatePrompt(phase, toolCallCount);
            const messages: Anthropic.MessageParam[] = [
                { role: 'user', content: statePrompt }
            ];

            // Tools only in investigate phase
            const toolsToUse = phase === 'investigate' ? tools : [];

            console.log(`[CTM Agent] Iteration ${iteration} | Phase: ${phase} | Facts: ${this.factStore.getFactCount()} | Tool calls: ${toolCallCount}`);

            // Log what we're sending (should be SMALL now)
            const promptTokensEstimate = Math.ceil(statePrompt.length / 4);
            console.log(`[CTM Agent] State prompt: ~${promptTokensEstimate} tokens (${statePrompt.length} chars)`);

            // Make API call
            const response = await this.anthropic.messages.create({
                model: 'claude-3-5-haiku-20241022',
                max_tokens: 4000,
                system: this.systemPrompt,
                tools: toolsToUse,
                messages: messages
            });

            totalInputTokens += response.usage.input_tokens;
            totalOutputTokens += response.usage.output_tokens;

            console.log(`[CTM Agent] Response: input=${response.usage.input_tokens}, output=${response.usage.output_tokens}, stop=${response.stop_reason}`);

            const textContent = response.content.find(block => block.type === 'text');
            const toolUses = response.content.filter(block => block.type === 'tool_use');

            // SYNTHESIS PHASE: Get text response and finish
            if (phase === 'synthesize') {
                if (textContent && textContent.type === 'text') {
                    finalResponse = textContent.text;
                    console.log(`[CTM Agent] ✓ Synthesis complete: ${finalResponse.length} chars`);

                    this.reportProgress({
                        phase: 'complete',
                        toolCallCount,
                        maxToolCalls: MAX_TOOL_CALLS,
                        message: 'Analysis complete!',
                        percentage: 100
                    });
                    break;
                }

                // If it tried to use tools in synthesis, just ask again
                if (toolUses.length > 0) {
                    console.log(`[CTM Agent] ⚠️ Ignoring tool calls in synthesis phase`);
                    continue;
                }
            }

            // INVESTIGATE PHASE: Handle tool calls
            if (phase === 'investigate' && toolUses.length > 0) {
                for (const toolUse of toolUses) {
                    if (toolUse.type !== 'tool_use') continue;

                    toolCallCount++;
                    console.log(`[CTM Agent] Tool call ${toolCallCount}/${MAX_TOOL_CALLS}: ${toolUse.name}`);

                    this.reportProgress({
                        phase: 'investigate',
                        toolCallCount,
                        maxToolCalls: MAX_TOOL_CALLS,
                        currentTool: toolUse.name,
                        message: `Analyzing ${this.formatToolName(toolUse.name)}...`,
                        percentage: Math.min(80, 10 + (toolCallCount / MAX_TOOL_CALLS) * 70)
                    });

                    // Execute tool
                    const result = await this.executeTool(toolUse.name, toolUse.input);

                    // CRITICAL: Extract facts and DELETE the raw result
                    const confirmation = await this.factStore.extractAndStore(toolUse.name, result);
                    console.log(`[CTM Agent] ${confirmation}`);
                    console.log(`[CTM Agent] Total facts: ${this.factStore.getFactCount()}`);

                    // Check hard cap
                    if (toolCallCount >= MAX_TOOL_CALLS) {
                        console.log(`[CTM Agent] Hit MAX_TOOL_CALLS - forcing synthesis`);
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
                    console.log(`[CTM Agent] ✓ Natural completion: ${finalResponse.length} chars`);

                    this.reportProgress({
                        phase: 'complete',
                        toolCallCount,
                        maxToolCalls: MAX_TOOL_CALLS,
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
            canContinue: completionReason !== 'natural' && contextQuality !== 'high',
            toolCallsUsed: toolCallCount,
            toolsUsed: this.factStore.getToolsCalled(),
            tokensUsed: totalInputTokens + totalOutputTokens
        };
    }

    /**
     * Build rawContext from facts for UI display
     */
    private buildRawContextFromFacts(): any {
        const facts = Array.from(this.factStore['facts'].values());
        const context: any = {
            file_path: this.config.filePath,
            line_start: this.config.lineStart,
            line_end: this.config.lineEnd
        };

        // Extract structured data from facts
        for (const fact of facts) {
            if (fact.id.startsWith('blame_') && !context.blame_commit) {
                context.blame_commit = { summary: fact.text };
            }
            if (fact.id.startsWith('pr_') && !fact.id.includes('_reason') && !fact.id.includes('_body') && !fact.id.includes('_discussion')) {
                if (!context.pull_request) {
                    const match = fact.text.match(/PR #(\d+)/);
                    context.pull_request = {
                        number: match ? parseInt(match[1]) : null,
                        summary: fact.text
                    };
                }
            }
            if (fact.id.startsWith('issue_') && !fact.id.includes('_desc') && !fact.id.includes('_body')) {
                if (!context.linked_issues) context.linked_issues = [];
                const match = fact.text.match(/Issue #(\d+)/);
                context.linked_issues.push({
                    number: match ? parseInt(match[1]) : null,
                    summary: fact.text
                });
            }
            if (fact.id.startsWith('origin_')) {
                context.origin = { summary: fact.text };
            }
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
     * Continue investigation with previous state
     */
    async continueInvestigation(previousState: InvestigationState): Promise<InvestigationResult> {
        console.log('[CTM Agent] Continuing investigation with previous state');
        console.log('[CTM Agent] Previous tools:', previousState.toolsUsed.join(', '));

        // Restore fact context from summary (simplified - in production you'd persist facts)
        // For now, we just continue with a fresh fact store but include the summary
        this.factStore.clear();

        // Add summary as a "meta fact"
        this.factStore['facts'].set('previous_summary', {
            id: 'previous_summary',
            text: `Previous investigation found: ${previousState.summary.substring(0, 500)}...`,
            source: 'continuation',
            category: 'other'
        });

        // Run investigation again
        return this.investigate();
    }

    /**
     * Get investigation state for continuation
     */
    async getInvestigationState(toolsUsed: string[]): Promise<{ summary: string; toolsUsed: string[] }> {
        return {
            summary: this.factStore.getFactsSummary(),
            toolsUsed
        };
    }

    /**
     * Ask a follow-up question
     */
    async askFollowUp(question: string, previousSummary: string): Promise<string> {
        console.log('[CTM Agent] Processing follow-up question:', question);

        const prompt = `## Follow-up Question

**Previous Analysis:**
${previousSummary}

**User Question:**
${question}

Answer based on the previous analysis. Be concise.`;

        const response = await this.anthropic.messages.create({
            model: 'claude-3-5-haiku-20241022',
            max_tokens: 2000,
            messages: [{ role: 'user', content: prompt }]
        });

        const textContent = response.content.find(block => block.type === 'text');
        return textContent && textContent.type === 'text' ? textContent.text : 'Unable to process follow-up.';
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
            'get_commit_diff': 'commit diff'
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

        console.log(`[CTM Agent] Executing ${toolName}`);
        const result = await this.mcpClient.callTool(toolName, translatedInput);

        console.groupCollapsed(`[CTM Agent] Tool result for ${toolName} (click to expand)`);
        console.log(JSON.stringify(result, null, 2));
        console.groupEnd();

        return result;
    }
}
