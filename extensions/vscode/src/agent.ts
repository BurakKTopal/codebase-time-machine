import Anthropic from '@anthropic-ai/sdk';
import { MCPClient } from './mcpClient';

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

// Configuration
const MAX_TOOL_CALLS = 12; // Cap based on actual tool calls, not iterations
const SYNTHESIS_THRESHOLD = 8; // Switch to synthesis after this many tool calls

// Agent phases - this is a HARD constraint, not advisory
type AgentPhase = 'investigate' | 'synthesize';

export class CTMAgent {
    private anthropic: Anthropic;
    private mcpClient: MCPClient;
    private config: AgentConfig;
    private conversationHistory: Anthropic.MessageParam[] = [];
    private progressCallback?: ProgressCallback;

    constructor(mcpClient: MCPClient, config: AgentConfig) {
        this.anthropic = new Anthropic({ apiKey: config.apiKey });
        this.mcpClient = mcpClient;
        this.config = config;
    }

    /**
     * Set a callback to receive progress updates during investigation
     */
    setProgressCallback(callback: ProgressCallback): void {
        this.progressCallback = callback;
    }

    /**
     * Report progress to the callback if set
     */
    private reportProgress(update: ProgressUpdate): void {
        if (this.progressCallback) {
            this.progressCallback(update);
        }
    }

    async investigate(): Promise<{ summary: string; rawContext: any }> {
        console.log('[CTM Agent] Starting investigation (FSM-based control)');
        console.log('[CTM Agent] File:', this.config.filePath);
        console.log('[CTM Agent] Lines:', this.config.lineStart, '-', this.config.lineEnd);
        console.log('[CTM Agent] Branch:', this.config.branch || 'unknown');

        // Get available tools from MCP server
        const tools = await this.getAvailableTools();
        console.log('[CTM Agent] Available tools:', tools.length);

        // Report initial progress
        this.reportProgress({
            phase: 'investigate',
            toolCallCount: 0,
            maxToolCalls: MAX_TOOL_CALLS,
            message: 'Starting investigation...',
            percentage: 5
        });

        // FSM state
        let phase: AgentPhase = 'investigate';
        let toolCallCount = 0;
        let iteration = 0;
        let finalResponse = '';
        let collectedContext: any = {};
        let totalInputTokens = 0;
        let totalOutputTokens = 0;

        // Initial prompt includes CLAUDE.md
        const initialPrompt = this.buildInitialPrompt();
        console.log('[CTM Agent] Initial prompt length:', initialPrompt.length, 'chars');

        // Add initial user message
        this.conversationHistory.push({ role: 'user', content: initialPrompt });

        // Main agent loop
        while (true) {
            iteration++;

            // Check phase transition BEFORE making the call
            if (phase === 'investigate' && toolCallCount >= SYNTHESIS_THRESHOLD) {
                phase = 'synthesize';
                console.log(`[CTM Agent] ═══════════════════════════════════════════════════`);
                console.log(`[CTM Agent] PHASE TRANSITION: investigate → synthesize`);
                console.log(`[CTM Agent] Tool calls made: ${toolCallCount}/${MAX_TOOL_CALLS}`);
                console.log(`[CTM Agent] ═══════════════════════════════════════════════════`);

                // Report phase transition
                this.reportProgress({
                    phase: 'synthesize',
                    toolCallCount,
                    maxToolCalls: MAX_TOOL_CALLS,
                    message: 'Synthesizing findings...',
                    percentage: 85
                });

                // Add synthesis prompt (short, identity-based, no CLAUDE.md)
                this.conversationHistory.push({
                    role: 'user',
                    content: this.buildSynthesisPrompt()
                });
            }

            // Hard constraint: tools ONLY in investigate phase
            const toolsToUse = phase === 'investigate' ? tools : [];

            console.log(`[CTM Agent] Iteration ${iteration} | Phase: ${phase} | Tools: ${toolsToUse.length > 0 ? 'ENABLED' : 'DISABLED'} | Tool calls: ${toolCallCount}`);

            // Build messages
            const messages = [...this.conversationHistory];
            const messagesSizeChars = JSON.stringify(messages).length;
            console.log(`[CTM Agent] Sending ${messages.length} messages (${(messagesSizeChars / 1024).toFixed(1)} KB)`);

            // Make API call
            const response = await this.anthropic.messages.create({
                model: 'claude-3-5-haiku-20241022',
                max_tokens: 4000,
                tools: toolsToUse,
                messages: messages
            });

            // Track tokens
            totalInputTokens += response.usage.input_tokens;
            totalOutputTokens += response.usage.output_tokens;
            console.log(`[CTM Agent] Tokens: +${response.usage.input_tokens}/${response.usage.output_tokens} | Total: ${totalInputTokens + totalOutputTokens}`);

            // Extract text content
            const textContent = response.content.find(block => block.type === 'text');
            const toolUses = response.content.filter(block => block.type === 'tool_use');

            if (textContent && textContent.type === 'text') {
                console.log('[CTM Agent] Text response:', textContent.text.substring(0, 150) + '...');
            }

            // SYNTHESIS PHASE: If we get any text, we're done
            if (phase === 'synthesize') {
                if (toolUses.length > 0) {
                    // IGNORE tool calls in synthesis phase - don't add to history, just re-ask
                    console.log(`[CTM Agent] ⚠️ IGNORING ${toolUses.length} tool calls in synthesis phase - re-asking`);

                    // Add a stronger reminder (don't add the tool_use response to history)
                    this.conversationHistory.push({
                        role: 'user',
                        content: `You are in SYNTHESIS MODE. Tools are unavailable. Write your final answer NOW using the evidence you already gathered. Do not attempt tool calls.`
                    });
                    continue; // Re-ask without processing tool calls
                }

                // Got text-only response in synthesis - we're done!
                if (textContent && textContent.type === 'text') {
                    finalResponse = textContent.text;
                    console.log(`[CTM Agent] ✓ Synthesis complete: ${finalResponse.length} chars`);

                    // Report completion
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

            // INVESTIGATE PHASE: Handle tool calls
            if (phase === 'investigate' && toolUses.length > 0) {
                console.log(`[CTM Agent] Processing ${toolUses.length} tool call(s)`);

                // Add assistant response to history
                this.conversationHistory.push({
                    role: 'assistant',
                    content: response.content
                });

                // Execute tool calls
                const toolResults: Anthropic.ToolResultBlockParam[] = [];
                for (const toolUse of toolUses) {
                    if (toolUse.type === 'tool_use') {
                        toolCallCount++;
                        console.log(`[CTM Agent] Tool ${toolCallCount}/${MAX_TOOL_CALLS}: ${toolUse.name}`);

                        // Report progress before tool execution
                        const progressPercentage = Math.min(10 + (toolCallCount / MAX_TOOL_CALLS) * 70, 80);
                        this.reportProgress({
                            phase: 'investigate',
                            toolCallCount,
                            maxToolCalls: MAX_TOOL_CALLS,
                            currentTool: toolUse.name,
                            message: `Calling ${this.formatToolName(toolUse.name)}... (${toolCallCount}/${MAX_TOOL_CALLS})`,
                            percentage: progressPercentage
                        });

                        const result = await this.executeTool(toolUse.name, toolUse.input);

                        // Collect context from various tools
                        if (toolUse.name === 'get_line_context' || toolUse.name === 'get_local_line_context') {
                            collectedContext = { ...collectedContext, ...result };
                        }

                        // Capture PR info from get_pr calls
                        if (toolUse.name === 'get_pr' && result && result.number) {
                            collectedContext.pull_request = result;
                            console.log(`[CTM Agent] Captured PR #${result.number} in context`);
                        }

                        // Capture issue info from get_issue calls
                        if (toolUse.name === 'get_issue' && result && result.number) {
                            if (!collectedContext.linked_issues) {
                                collectedContext.linked_issues = [];
                            }
                            // Avoid duplicates
                            if (!collectedContext.linked_issues.some((i: any) => i.number === result.number)) {
                                collectedContext.linked_issues.push(result);
                                console.log(`[CTM Agent] Captured issue #${result.number} in context`);
                            }
                        }

                        // Capture PR references from search_prs_for_commit
                        if (toolUse.name === 'search_prs_for_commit' && result && result.items && result.items.length > 0) {
                            // Store the first PR if we don't have one yet
                            if (!collectedContext.pull_request && result.items[0]) {
                                collectedContext.pull_request = result.items[0];
                                console.log(`[CTM Agent] Captured PR #${result.items[0].number} from search in context`);
                            }
                        }

                        const truncatedResult = this.truncateToolResult(toolUse.name, result);
                        toolResults.push({
                            type: 'tool_result',
                            tool_use_id: toolUse.id,
                            content: truncatedResult
                        });

                        // Check if we hit the hard cap
                        if (toolCallCount >= MAX_TOOL_CALLS) {
                            console.log(`[CTM Agent] ⚠️ Hit MAX_TOOL_CALLS (${MAX_TOOL_CALLS}) - forcing synthesis`);
                            phase = 'synthesize';
                            break;
                        }
                    }
                }

                // Add tool results to history
                this.conversationHistory.push({
                    role: 'user',
                    content: toolResults
                });

                // If we just hit the cap, add synthesis prompt
                if (phase === 'synthesize') {
                    this.conversationHistory.push({
                        role: 'user',
                        content: this.buildSynthesisPrompt()
                    });
                }

                continue;
            }

            // INVESTIGATE PHASE: No tool calls = natural completion
            if (phase === 'investigate' && toolUses.length === 0) {
                if (textContent && textContent.type === 'text') {
                    // Agent finished naturally during investigation
                    finalResponse = textContent.text;
                    console.log(`[CTM Agent] ✓ Natural completion: ${finalResponse.length} chars`);

                    // Report completion
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

            // Safety: prevent infinite loops
            if (iteration > 20) {
                console.error('[CTM Agent] ERROR: Too many iterations, breaking');
                finalResponse = 'Investigation exceeded maximum iterations.';
                break;
            }
        }

        // Log summary
        console.log('\n========== INVESTIGATION SUMMARY ==========');
        console.log(`Iterations: ${iteration}`);
        console.log(`Tool calls: ${toolCallCount}`);
        console.log(`Total tokens: ${totalInputTokens + totalOutputTokens}`);
        console.log(`Final response: ${finalResponse.length} chars`);
        console.log('============================================\n');

        return {
            summary: finalResponse || 'Investigation completed but no summary was generated.',
            rawContext: collectedContext
        };
    }

    private buildSynthesisPrompt(): string {
        // Short, identity-based prompt for synthesis phase
        // NO CLAUDE.md - that encourages investigation
        return `You are now in SYNTHESIS MODE.

Investigation is complete. Tools are unavailable.
Your job is to write the final answer using ONLY the evidence already gathered.

Structure your answer as:

**What & When:** What is this code? When was it added? (commit SHA, author, date)
**Why:** What problem did it solve? Any linked issues or PRs?
**How:** How does this code solve the problem?
**Context:** Any related changes or recommendations?

Do NOT apologize for missing information.
Do NOT request more data.
Synthesize what you have into a clear, complete answer NOW.`;
    }

    /**
     * Ask a follow-up question based on the previous investigation
     * @param question The user's follow-up question
     * @param previousContext The previous investigation summary
     * @returns The answer to the follow-up question
     */
    async askFollowUp(question: string, previousContext: string): Promise<string> {
        console.log('[CTM Agent] Starting follow-up investigation');
        console.log('[CTM Agent] Question:', question);

        // Report starting
        this.reportProgress({
            phase: 'investigate',
            toolCallCount: 0,
            maxToolCalls: 5,
            message: 'Processing follow-up question...',
            percentage: 10
        });

        // Get available tools
        const tools = await this.getAvailableTools();

        // Build follow-up prompt
        const followUpPrompt = `You previously investigated code at:
- **Repository:** ${this.config.owner}/${this.config.repo}
- **File:** ${this.config.filePath}
- **Lines:** ${this.config.lineStart}-${this.config.lineEnd}
- **Branch:** ${this.config.branch || 'HEAD'}

## Previous Investigation Summary

${previousContext}

## User's Follow-up Question

${question}

## Your Task

Answer the user's follow-up question. You can use the same investigation tools (get_local_line_context, get_commit_diff, etc.) to gather more information if needed. Keep your answer concise but thorough. You have 5 iterations maximum for this follow-up.`;

        // Reset conversation history for follow-up
        const followUpHistory: Anthropic.MessageParam[] = [{
            role: 'user',
            content: followUpPrompt
        }];

        const maxFollowUpIterations = 5;
        let iteration = 0;
        let finalResponse = '';

        while (iteration < maxFollowUpIterations) {
            iteration++;
            console.log(`[CTM Agent Follow-up] Iteration ${iteration}/${maxFollowUpIterations}`);

            // Disable tools at final iteration to force answer
            const toolsToUse = iteration >= maxFollowUpIterations ? [] : tools;

            const response = await this.anthropic.messages.create({
                model: 'claude-3-5-haiku-20241022',
                max_tokens: 4000,
                tools: toolsToUse,
                messages: followUpHistory
            });

            console.log('[CTM Agent Follow-up] Stop reason:', response.stop_reason);

            // Process response
            const textContent = response.content.find(block => block.type === 'text');
            if (textContent && textContent.type === 'text') {
                console.log('[CTM Agent Follow-up] Response:', textContent.text.substring(0, 200) + '...');
            }

            // Handle tool calls
            const toolUses = response.content.filter(block => block.type === 'tool_use');

            if (toolUses.length > 0 && iteration < maxFollowUpIterations) {
                console.log('[CTM Agent Follow-up] Executing', toolUses.length, 'tool(s)');

                // Add assistant message to history
                followUpHistory.push({
                    role: 'assistant',
                    content: response.content
                });

                // Execute tool calls
                const toolResults: Anthropic.ToolResultBlockParam[] = [];
                let toolCount = 0;
                for (const toolUse of toolUses) {
                    if (toolUse.type === 'tool_use') {
                        toolCount++;
                        console.log('[CTM Agent Follow-up] Executing:', toolUse.name);

                        // Report progress
                        const progressPercentage = 20 + (iteration / maxFollowUpIterations) * 60;
                        this.reportProgress({
                            phase: 'investigate',
                            toolCallCount: toolCount,
                            maxToolCalls: 5,
                            currentTool: toolUse.name,
                            message: `Calling ${this.formatToolName(toolUse.name)}...`,
                            percentage: progressPercentage
                        });

                        const result = await this.executeTool(toolUse.name, toolUse.input);

                        // Truncate result
                        const truncatedResult = this.truncateToolResult(toolUse.name, result);

                        toolResults.push({
                            type: 'tool_result',
                            tool_use_id: toolUse.id,
                            content: truncatedResult
                        });
                    }
                }

                // Add tool results to history
                followUpHistory.push({
                    role: 'user',
                    content: toolResults
                });
            } else {
                // No more tool calls or at max iterations
                const finalText = response.content.find(block => block.type === 'text');
                if (finalText && finalText.type === 'text') {
                    finalResponse = finalText.text;
                    console.log('[CTM Agent Follow-up] Got final response:', finalResponse.length, 'chars');

                    // Report completion
                    this.reportProgress({
                        phase: 'complete',
                        toolCallCount: 0,
                        maxToolCalls: 5,
                        message: 'Done!',
                        percentage: 100
                    });
                }
                break;
            }
        }

        return finalResponse || 'I was unable to answer the follow-up question.';
    }

    private buildInitialPrompt(): string {
        const fs = require('fs');
        const path = require('path');

        // Load compact CLAUDE.md from the bundled copy in the extension
        const claudeMdPath = path.join(__dirname, 'CLAUDE.md');
        let claudeGuide = '';
        try {
            claudeGuide = fs.readFileSync(claudeMdPath, 'utf-8');
            console.log(`[CTM Agent] Loaded bundled CLAUDE.md: ${claudeGuide.length} chars`);
        } catch (error) {
            console.error('[CTM Agent] CRITICAL: Could not load bundled CLAUDE.md:', error);
            console.error('[CTM Agent] Tried path:', claudeMdPath);
            claudeGuide = 'You are investigating code. Use get_local_line_context with history_depth=5-10 to start.';
        }

        // Simple task definition - all guidance is in CLAUDE.md
        return `${claudeGuide}

---

## Your Investigation Task

Investigate this code:
- **Repository:** ${this.config.owner}/${this.config.repo}
- **File:** ${this.config.filePath}
- **Lines:** ${this.config.lineStart}-${this.config.lineEnd}
- **Branch:** ${this.config.branch || 'HEAD'}
- **Local Path:** ${this.config.repoPath}

**You have ${MAX_TOOL_CALLS} tool calls before synthesis begins.** You will NOT control when investigation ends. When synthesis begins, you must stop immediately. Begin your investigation now.`;
    }

    private async getAvailableTools(): Promise<Anthropic.Tool[]> {
        // Get tools from MCP server
        const mcpTools = await this.mcpClient.listTools();

        console.log('[CTM Agent] Available MCP tools:', mcpTools.length);

        // Convert all MCP tools to Anthropic format
        // Agent has access to both GitHub API tools and local git tools
        const anthropicTools: Anthropic.Tool[] = mcpTools.map(tool => ({
            name: tool.name,
            description: tool.description || `MCP tool: ${tool.name}`,
            input_schema: tool.inputSchema as Anthropic.Tool.InputSchema
        }));

        return anthropicTools;
    }

    private truncateToolResult(toolName: string, result: any): string {
        // Intelligently truncate tool results to reduce token usage
        // Keep only the most relevant information for the agent

        const MAX_CONTENT_LENGTH = 2000; // Max chars for large text fields
        const MAX_ARRAY_ITEMS = 10; // Max items to keep from arrays

        if (typeof result !== 'object' || result === null) {
            const str = JSON.stringify(result);
            return str.length > MAX_CONTENT_LENGTH
                ? str.substring(0, MAX_CONTENT_LENGTH) + '... [truncated]'
                : str;
        }

        const truncated: any = {};

        // Handle get_local_line_context and get_line_context - create compact text summary
        if (toolName === 'get_local_line_context' || toolName === 'get_line_context') {
            const lines: string[] = [];

            // Code content
            if (result.current_content || result.line_content) {
                lines.push('CODE:');
                lines.push(result.current_content || result.line_content);
                lines.push('');
            }

            // Blame commit (last touch - may not be the original introduction!)
            if (result.blame_commit) {
                const bc = result.blame_commit;
                const shortSha = bc.sha?.substring(0, 8) || 'unknown';
                const date = bc.date?.substring(0, 10) || 'unknown';
                const firstLine = bc.message?.split('\n')[0] || '';
                lines.push(`BLAME (last touch): ${shortSha} by ${bc.author} on ${date}`);
                lines.push(`  "${this.truncateString(firstLine, 100)}"`);
                lines.push('');
            }

            // Historical commits - KEY for finding when code was actually introduced
            if (result.historical_commits && Array.isArray(result.historical_commits) && result.historical_commits.length > 0) {
                lines.push(`HISTORY (${result.historical_commits.length} commits before blame):`);
                result.historical_commits.slice(0, 10).forEach((commit: any, idx: number) => {
                    const shortSha = commit.sha?.substring(0, 8) || 'unknown';
                    const date = commit.date?.substring(0, 10) || 'unknown';
                    const firstLine = commit.message?.split('\n')[0] || '';
                    const stats = commit.stats ? ` [+${commit.stats.additions}/-${commit.stats.deletions}]` : '';
                    lines.push(`  ${idx + 1}. ${shortSha} ${date}${stats} "${this.truncateString(firstLine, 80)}"`);
                });
                lines.push('');
            }

            // PR context
            if (result.pull_request) {
                const pr = result.pull_request;
                lines.push(`PR: #${pr.number} "${this.truncateString(pr.title || '', 100)}"`);
                if (pr.body) {
                    lines.push(`  ${this.truncateString(pr.body, 300)}`);
                }
                lines.push('');
            } else {
                lines.push('PR: None found (likely direct commit to main)');
                lines.push('');
            }

            // Linked issues
            if (result.linked_issues && result.linked_issues.length > 0) {
                lines.push('LINKED ISSUES:');
                result.linked_issues.slice(0, 3).forEach((issue: any) => {
                    lines.push(`  #${issue.number}: ${this.truncateString(issue.title || '', 80)}`);
                    if (issue.body) {
                        lines.push(`    ${this.truncateString(issue.body, 200)}`);
                    }
                });
                lines.push('');
            }

            // Hints from the tool
            if (result.context_availability?.suggestions && result.context_availability.suggestions.length > 0) {
                lines.push(`SUGGESTIONS: ${result.context_availability.suggestions.join('; ')}`);
            }

            return lines.join('\n');
        }

        // For file content tools, truncate aggressively
        if (toolName === 'get_github_file' || toolName === 'get_file_at_commit') {
            if (result.content) {
                const lines = result.content.split('\n');
                if (lines.length > 50) {
                    truncated.content = lines.slice(0, 50).join('\n') + `\n... [${lines.length - 50} more lines truncated]`;
                } else {
                    truncated.content = result.content;
                }
            }
            if (result.path) truncated.path = result.path;
            if (result.sha) truncated.sha = result.sha;
            return JSON.stringify(truncated);
        }

        // For commit history tools, create compact text list
        if (toolName === 'get_github_file_history' || toolName === 'trace_file_history') {
            if (result.commits && Array.isArray(result.commits)) {
                const lines: string[] = [];
                lines.push(`COMMIT HISTORY (${result.commits.length} total):`);
                result.commits.slice(0, 15).forEach((c: any, idx: number) => {
                    const shortSha = c.sha?.substring(0, 8) || 'unknown';
                    const date = c.date?.substring(0, 10) || 'unknown';
                    const firstLine = c.message?.split('\n')[0] || '';
                    const stats = c.stats ? ` [+${c.stats.additions}/-${c.stats.deletions}]` : '';
                    lines.push(`  ${idx + 1}. ${shortSha} ${date}${stats} "${this.truncateString(firstLine, 80)}"`);
                });
                if (result.commits.length > 15) {
                    lines.push(`  ... ${result.commits.length - 15} more commits not shown`);
                }
                return lines.join('\n');
            }
            return JSON.stringify(truncated);
        }

        // For get_commit, create compact text summary
        if (toolName === 'get_commit' || toolName === 'get_github_commit') {
            const lines: string[] = [];
            lines.push(`COMMIT: ${result.sha?.substring(0, 8)} by ${result.author} on ${result.date?.substring(0, 10)}`);
            if (result.message) {
                lines.push(`MESSAGE: ${this.truncateString(result.message, 500)}`);
            }
            if (result.stats) {
                lines.push(`CHANGES: +${result.stats.additions || 0}/-${result.stats.deletions || 0} lines`);
            }
            if (result.files && Array.isArray(result.files)) {
                lines.push(`FILES (${result.files.length}): ${result.files.slice(0, 10).map((f: any) => f.path || f).join(', ')}`);
            }
            return lines.join('\n');
        }

        // For get_commit_diff, show the diff but truncate intelligently
        if (toolName === 'get_commit_diff') {
            const lines: string[] = [];
            if (result.commit) {
                lines.push(`COMMIT: ${result.commit.sha?.substring(0, 8)} by ${result.commit.author}`);
                lines.push(`MESSAGE: ${this.truncateString(result.commit.message, 300)}`);
                lines.push('');
            }
            if (result.diff) {
                const diffLines = result.diff.split('\n');
                if (diffLines.length > 100) {
                    lines.push(`DIFF (showing first 100 of ${diffLines.length} lines):`);
                    lines.push(diffLines.slice(0, 100).join('\n'));
                    lines.push(`... ${diffLines.length - 100} more lines not shown`);
                } else {
                    lines.push('DIFF:');
                    lines.push(result.diff);
                }
            }
            return lines.join('\n');
        }

        // Default: truncate all string fields and limit arrays
        for (const key in result) {
            if (typeof result[key] === 'string') {
                truncated[key] = this.truncateString(result[key], MAX_CONTENT_LENGTH);
            } else if (Array.isArray(result[key])) {
                truncated[key] = result[key].slice(0, MAX_ARRAY_ITEMS);
                if (result[key].length > MAX_ARRAY_ITEMS) {
                    truncated[key + '_truncated'] = `Showing ${MAX_ARRAY_ITEMS} of ${result[key].length} items`;
                }
            } else {
                truncated[key] = result[key];
            }
        }

        return JSON.stringify(truncated);
    }

    private truncateString(str: string | undefined | null, maxLength: number): string {
        if (!str) return '';
        if (str.length <= maxLength) return str;
        return str.substring(0, maxLength) + '... [truncated]';
    }

    /**
     * Format a tool name for display in progress messages
     */
    private formatToolName(toolName: string): string {
        // Map tool names to human-readable descriptions
        const toolLabels: Record<string, string> = {
            'get_local_line_context': 'line context',
            'get_line_context': 'line context',
            'get_commit': 'commit details',
            'get_commit_diff': 'commit diff',
            'get_github_commit': 'commit details',
            'get_pr': 'pull request',
            'get_issue': 'issue',
            'search_prs_for_commit': 'PR search',
            'trace_file_history': 'file history',
            'get_github_file_history': 'file history',
            'get_github_file': 'file content',
            'blame_with_context': 'blame info',
            'explain_file': 'file overview',
            'get_code_context': 'code context',
            'get_code_owners': 'code owners',
            'pickaxe_search': 'code origin search',
        };

        return toolLabels[toolName] || toolName.replace(/_/g, ' ');
    }

    private async executeTool(toolName: string, input: any): Promise<any> {
        // Auto-translate parameters for local tools
        const localTools = [
            'get_commit_diff',
            'trace_file_history',
            'get_file_at_commit',
            'blame_with_context',
            'get_file_symbols',
            'trace_symbol_history',
            'get_repo_info',
            'list_branches',
            'get_commit',
            'explain_commit'
        ];

        let translatedInput = input;

        if (localTools.includes(toolName)) {
            // Agent used GitHub-style parameters, translate to local-style
            if (input.owner && input.repo && !input.repo_path) {
                console.log(`[CTM Agent] Auto-translating GitHub params to local params for ${toolName}`);
                translatedInput = { ...input };
                delete translatedInput.owner;
                delete translatedInput.repo;
                translatedInput.repo_path = this.config.repoPath;

                // Translate path to file_path if needed
                if (translatedInput.path) {
                    translatedInput.file_path = translatedInput.path;
                    delete translatedInput.path;
                }

                console.log(`[CTM Agent] Translated input:`, translatedInput);
            }
        }

        // Call the MCP tool
        const result = await this.mcpClient.callTool(toolName, translatedInput);

        console.groupCollapsed(`[CTM Agent] 📦 Tool result for ${toolName} (click to expand)`);
        console.log(JSON.stringify(result, null, 2));
        console.groupEnd();

        return result;
    }
}
