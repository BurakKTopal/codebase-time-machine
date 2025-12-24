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

const maxIterations = 10;

export class CTMAgent {
    private anthropic: Anthropic;
    private mcpClient: MCPClient;
    private config: AgentConfig;
    private conversationHistory: Anthropic.MessageParam[] = [];

    constructor(mcpClient: MCPClient, config: AgentConfig) {
        this.anthropic = new Anthropic({ apiKey: config.apiKey });
        this.mcpClient = mcpClient;
        this.config = config;
    }

    async investigate(): Promise<{ summary: string; rawContext: any }> {
        console.log('[CTM Agent] Starting investigation');
        console.log('[CTM Agent] File:', this.config.filePath);
        console.log('[CTM Agent] Lines:', this.config.lineStart, '-', this.config.lineEnd);
        console.log('[CTM Agent] Branch:', this.config.branch || 'unknown');

        // Get available tools from MCP server
        const tools = await this.getAvailableTools();
        console.log('[CTM Agent] Available tools:', tools.length);

        // Initial prompt
        const initialPrompt = this.buildInitialPrompt();
        console.log('[CTM Agent] Initial prompt length:', initialPrompt.length, 'chars');

        // Run agent loop
        let iteration = 0;
        let finalResponse = '';
        let collectedContext: any = {};
        let totalInputTokens = 0;
        let totalOutputTokens = 0;

        while (iteration < maxIterations) {
            iteration++;
            console.log(`[CTM Agent] Iteration ${iteration}/${maxIterations}`);

            // Build messages array
            // IMPORTANT: Only add a new user message if the last message in history is NOT already a user message
            // (After tool results are added, the last message is already a user message)
            let messages: Anthropic.MessageParam[];

            const lastMessage = this.conversationHistory[this.conversationHistory.length - 1];
            const needsUserMessage = !lastMessage || lastMessage.role !== 'user';

            if (needsUserMessage) {
                // First iteration or after Claude's text-only response - add user prompt
                let userMessage: string;

                if (iteration === 1) {
                    userMessage = initialPrompt;
                } else if (iteration >= maxIterations - 1) {
                    // Final iterations - demand synthesis NOW
                    userMessage = `<system_reminder>CRITICAL: This is iteration ${iteration} of ${maxIterations}. You are at or near the maximum iteration limit.

You MUST provide your final answer NOW. Do NOT make any more tool calls.

Synthesize everything you have learned so far and provide a complete 3-5 paragraph answer that explains:
1. What this code is and when it was added
2. WHY it exists (the problem it solved)
3. HOW it solves the problem
4. Any relevant context or recommendations

Use the information you have already gathered. If you don't have all the details, provide the best answer you can with what you know.</system_reminder>\n\nProvide your final answer now. Do not use any tools.`;
                } else {
                    // Add iteration reminder
                    const remaining = maxIterations - iteration;
                    let reminder = `<system_reminder>Iteration ${iteration}/${maxIterations}. ${remaining} iterations remaining. `;

                    if (iteration >= maxIterations - 3) {
                        reminder += `You're running low on iterations - start synthesizing your findings and preparing final answer.`;
                    } else if (iteration >= maxIterations / 2) {
                        reminder += `Halfway through - ensure you're digging deep, not just gathering surface info.`;
                    } else {
                        reminder += `Plenty of iterations left - investigate thoroughly, read diffs, check historical_commits.`;
                    }

                    reminder += `</system_reminder>\n\nContinue your investigation.`;
                    userMessage = reminder;
                }

                console.log('[CTM Agent] Adding new user message to history (last message was assistant or empty)');

                // CRITICAL: Add the user message to conversation history so it's persisted
                const userMessageParam: Anthropic.MessageParam = { role: 'user', content: userMessage };
                this.conversationHistory.push(userMessageParam);

                messages = [...this.conversationHistory];
            } else {
                // Last message is already user message (tool results) - don't add another
                console.log('[CTM Agent] Using existing tool_results as user message (not adding duplicate user message)');
                messages = [...this.conversationHistory];
            }

            // Calculate message sizes for verification
            const messagesSizeChars = JSON.stringify(messages).length;
            const messagesSizeKB = (messagesSizeChars / 1024).toFixed(2);
            console.log(`[CTM Agent] Sending ${messages.length} messages to Claude (${messagesSizeChars} chars / ${messagesSizeKB} KB)`);
            console.log(`[CTM Agent] History: ${this.conversationHistory.length} messages in conversation history`);

            // Log message structure for debugging
            const messageStructure = messages.map(m => m.role).join(' → ');
            console.log(`[CTM Agent] Message flow: ${messageStructure}`);

            // Disable tools at final iterations to force synthesis
            const toolsToUse = iteration >= maxIterations - 1 ? [] : tools;
            if (toolsToUse.length === 0 && iteration >= maxIterations - 1) {
                console.log(`[CTM Agent] Tools DISABLED - forcing final synthesis (iteration ${iteration}/${maxIterations})`);
            }

            const response = await this.anthropic.messages.create({
                model: 'claude-3-5-haiku-20241022',
                max_tokens: 4000,
                tools: toolsToUse,
                messages: messages
            });

            console.log('[CTM Agent] Response stop_reason:', response.stop_reason);
            console.log('[CTM Agent] Response usage:', response.usage);

            // Track token usage with detailed breakdown
            const iterationInputTokens = response.usage.input_tokens;
            const iterationOutputTokens = response.usage.output_tokens;
            totalInputTokens += iterationInputTokens;
            totalOutputTokens += iterationOutputTokens;

            console.log(`[CTM Agent] This iteration - Input: ${iterationInputTokens} tokens, Output: ${iterationOutputTokens} tokens`);
            console.log(`[CTM Agent] CUMULATIVE - Input: ${totalInputTokens}, Output: ${totalOutputTokens}, Total: ${totalInputTokens + totalOutputTokens}`);

            // Estimate chars-to-tokens ratio for verification (roughly 4 chars per token)
            const estimatedTokens = Math.round(messagesSizeChars / 4);
            console.log(`[CTM Agent] Verification: ${messagesSizeChars} chars ≈ ${estimatedTokens} estimated tokens vs ${iterationInputTokens} actual input tokens`);

            // Process response
            const textContent = response.content.find(block => block.type === 'text');
            if (textContent && textContent.type === 'text') {
                console.log('[CTM Agent] Claude says:', textContent.text.substring(0, 200) + '...');
            }

            // Handle tool calls
            const toolUses = response.content.filter(block => block.type === 'tool_use');

            console.log(`[CTM Agent] Response content blocks: ${response.content.length} (${response.content.map(b => b.type).join(', ')})`);

            if (toolUses.length > 0) {
                console.log('[CTM Agent] Claude wants to use', toolUses.length, 'tool(s)');

                // If we're at max iterations and agent is still trying to use tools, force a final summary
                if (iteration >= maxIterations) {
                    console.log('[CTM Agent] WARNING: At max iterations but agent still wants to use tools. Forcing final summary...');

                    // DON'T add the tool_use assistant message to history (would break pairing)
                    // Instead, make emergency call with existing history + demand for summary

                    const emergencyMessages: Anthropic.MessageParam[] = [
                        ...this.conversationHistory,
                        {
                            role: 'user',
                            content: `EMERGENCY STOP: You have reached the maximum iteration limit (${maxIterations}/${maxIterations}).

Based on ALL the context you have gathered so far, provide your final summary RIGHT NOW.

You MUST provide a complete answer in 3-5 paragraphs covering:
1. What this code is and when it was added (commit, author, date)
2. WHY it exists - what problem did it solve?
3. HOW it solves the problem - implementation details
4. Any relevant context, recommendations, or caveats

Use the information from your previous tool calls. If you don't have all details, provide the best answer you can with what you gathered.

DO NOT say you need more information. DO NOT attempt any more tool calls. Synthesize what you have NOW.`
                        }
                    ];

                    // Make one emergency call to force a text response (NO TOOLS available)
                    console.log('[CTM Agent] Making emergency call for final summary (tools disabled)...');
                    const emergencyResponse = await this.anthropic.messages.create({
                        model: 'claude-3-5-haiku-20241022',
                        max_tokens: 4000,
                        tools: [], // Explicitly disable tools
                        messages: emergencyMessages
                    });

                    const emergencyText = emergencyResponse.content.find(block => block.type === 'text');
                    if (emergencyText && emergencyText.type === 'text') {
                        finalResponse = emergencyText.text;
                        console.log('[CTM Agent] Emergency summary generated:', finalResponse.length, 'chars');
                    } else {
                        console.error('[CTM Agent] ERROR: Emergency call did not return text!');
                        finalResponse = 'Investigation reached max iterations but failed to generate emergency summary.';
                    }

                    break;
                }

                // Add assistant message to history
                this.conversationHistory.push({
                    role: 'assistant',
                    content: response.content
                });

                // Execute tool calls
                const toolResults: Anthropic.ToolResultBlockParam[] = [];
                for (const toolUse of toolUses) {
                    if (toolUse.type === 'tool_use') {
                        console.log('[CTM Agent] Executing tool:', toolUse.name);
                        console.log('[CTM Agent] Tool input:', JSON.stringify(toolUse.input, null, 2));

                        const result = await this.executeTool(toolUse.name, toolUse.input);

                        // Store context if it's get_line_context or get_local_line_context
                        if (toolUse.name === 'get_line_context' || toolUse.name === 'get_local_line_context') {
                            collectedContext = { ...collectedContext, ...result };
                        }

                        console.log('[CTM Agent] Tool result keys:', Object.keys(result));

                        // Truncate tool result to reduce token usage
                        const truncatedResult = this.truncateToolResult(toolUse.name, result);
                        const originalSize = JSON.stringify(result).length;
                        const truncatedSize = truncatedResult.length;
                        console.log(`[CTM Agent] Tool result size: ${originalSize} -> ${truncatedSize} chars (${Math.round((1 - truncatedSize / originalSize) * 100)}% reduction)`);

                        toolResults.push({
                            type: 'tool_result',
                            tool_use_id: toolUse.id,
                            content: truncatedResult
                        });
                    }
                }

                // Add tool results to history
                this.conversationHistory.push({
                    role: 'user',
                    content: toolResults
                });

                // PRUNING DISABLED FOR TESTING - keeping full conversation history
                // Prune conversation history to prevent unbounded growth
                // CRITICAL: Keep complete conversation turns (assistant + user pairs) to maintain tool_use/tool_result pairing
                const MAX_HISTORY_TURNS = 3; // Keep last 3 complete turns (6 messages: 3 assistant + 3 user)
                const maxHistoryMessages = MAX_HISTORY_TURNS * 2; // Each turn = assistant + user message

                if (false && this.conversationHistory.length > maxHistoryMessages + 1) {
                    console.log('[CTM Agent] === PRUNING DEBUG ===');
                    console.log('[CTM Agent] History before pruning:', this.conversationHistory.map(m => m.role).join(' → '));
                    console.log('[CTM Agent] Total messages:', this.conversationHistory.length);

                    // Structure: [initial_user, assistant1, user1, assistant2, user2, ...]
                    // We must keep complete (assistant, user) pairs to avoid breaking tool_use/tool_result pairing

                    const firstMessage = this.conversationHistory[0]; // Initial user prompt
                    console.log('[CTM Agent] First message role:', firstMessage?.role);

                    const withoutFirst = this.conversationHistory.slice(1); // All messages after initial
                    console.log('[CTM Agent] Messages after first:', withoutFirst.length);

                    // Each pair is (assistant, user), so we need an even number
                    // Keep the last N pairs
                    const pairsToKeep = Math.min(MAX_HISTORY_TURNS, Math.floor(withoutFirst.length / 2));
                    const messagesToKeep = pairsToKeep * 2;
                    console.log('[CTM Agent] Keeping', pairsToKeep, 'pairs =', messagesToKeep, 'messages');

                    // Get the last N complete pairs (skip any trailing unpaired message)
                    const recentMessages = withoutFirst.slice(-messagesToKeep);
                    console.log('[CTM Agent] Recent messages:', recentMessages.map(m => m.role).join(' → '));

                    // Verify we're starting with an assistant message (not orphaned user message)
                    if (recentMessages.length > 0 && recentMessages[0].role !== 'assistant') {
                        console.error('[CTM Agent] ERROR: Pruning would create orphaned tool_result! Skipping pruning.');
                        console.error('[CTM Agent] First recent message role:', recentMessages[0].role);
                    } else {
                        const prunedCount = withoutFirst.length - recentMessages.length;
                        console.log(`[CTM Agent] Pruning ${prunedCount} old messages`);
                        this.conversationHistory = [firstMessage, ...recentMessages];
                        console.log('[CTM Agent] History after pruning:', this.conversationHistory.map(m => m.role).join(' → '));
                        console.log('[CTM Agent] Total after pruning:', this.conversationHistory.length);
                    }
                    console.log('[CTM Agent] === END PRUNING DEBUG ===');
                }
            } else {
                // No more tool calls, Claude has finished
                console.log('[CTM Agent] No tool uses - investigation complete');

                const finalText = response.content.find(block => block.type === 'text');
                if (finalText && finalText.type === 'text') {
                    finalResponse = finalText.text;
                    console.log(`[CTM Agent] Final response captured: ${finalResponse.length} chars`);
                } else {
                    console.error('[CTM Agent] ERROR: No text block in final response!');
                    console.error('[CTM Agent] Response content:', JSON.stringify(response.content, null, 2));
                }

                break;
            }
        }

        if (iteration >= maxIterations) {
            console.log('[CTM Agent] WARNING: Reached max iterations without natural completion');
            console.log('[CTM Agent] Attempting to extract final response from conversation history...');
            // Extract last text response
            for (let i = this.conversationHistory.length - 1; i >= 0; i--) {
                const msg = this.conversationHistory[i];
                if (msg.role === 'assistant' && Array.isArray(msg.content)) {
                    const textBlock = msg.content.find(block => block.type === 'text');
                    if (textBlock && textBlock.type === 'text') {
                        finalResponse = textBlock.text;
                        console.log(`[CTM Agent] Extracted ${finalResponse.length} chars from history message ${i}`);
                        break;
                    }
                }
            }
            if (!finalResponse) {
                console.error('[CTM Agent] ERROR: Could not find any text in conversation history!');
            }
        }

        console.log('[CTM Agent] Final response length:', finalResponse.length, 'chars');

        // Log final token usage summary
        console.log('\n========== TOKEN USAGE SUMMARY ==========');
        console.log(`Total iterations: ${iteration}`);
        console.log(`Total input tokens: ${totalInputTokens}`);
        console.log(`Total output tokens: ${totalOutputTokens}`);
        console.log(`TOTAL TOKENS: ${totalInputTokens + totalOutputTokens}`);
        console.log(`Average per iteration: ${Math.round((totalInputTokens + totalOutputTokens) / iteration)} tokens`);
        console.log('=========================================\n');

        return {
            summary: finalResponse || 'Investigation completed but no summary was generated.',
            rawContext: collectedContext
        };
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

**You have ${maxIterations} iterations.** Follow the 5-step investigation strategy above. Begin your investigation now.`;
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
