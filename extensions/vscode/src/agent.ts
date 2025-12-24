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
        const maxIterations = 10;
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
                let userMessage = iteration === 1 ? initialPrompt : 'Continue your investigation.';
                if (iteration === maxIterations - 5) {
                    userMessage = `You're at iteration ${iteration} of ${maxIterations}. If you have sufficient context to answer the question, provide your final summary now. Otherwise, continue investigating efficiently.`;
                } else if (iteration === maxIterations - 3) {
                    const remaining = maxIterations - iteration;
                    userMessage = `IMPORTANT: You have only ${remaining} iterations remaining. Start preparing your final summary based on what you've found so far. If you have gathered sufficient context, provide your answer now.`;
                } else if (iteration === maxIterations - 1) {
                    userMessage = 'CRITICAL: This is your LAST iteration. You MUST provide a final summary now with all the context you\'ve gathered. Do NOT make any more tool calls.';
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

            const response = await this.anthropic.messages.create({
                model: 'claude-sonnet-4-5-20250929',
                max_tokens: 4000,
                tools: tools,
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

            if (toolUses.length > 0) {
                console.log('[CTM Agent] Claude wants to use', toolUses.length, 'tool(s)');

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

                // Prune conversation history to prevent unbounded growth
                // CRITICAL: Keep complete conversation turns (assistant + user pairs) to maintain tool_use/tool_result pairing
                const MAX_HISTORY_TURNS = 3; // Keep last 3 complete turns (6 messages: 3 assistant + 3 user)
                const maxHistoryMessages = MAX_HISTORY_TURNS * 2; // Each turn = assistant + user message

                if (this.conversationHistory.length > maxHistoryMessages + 1) {
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
                console.log('[CTM Agent] Investigation complete');

                const finalText = response.content.find(block => block.type === 'text');
                if (finalText && finalText.type === 'text') {
                    finalResponse = finalText.text;
                }

                break;
            }
        }

        if (iteration >= maxIterations) {
            console.log('[CTM Agent] WARNING: Reached max iterations');
            // Extract last text response
            for (let i = this.conversationHistory.length - 1; i >= 0; i--) {
                const msg = this.conversationHistory[i];
                if (msg.role === 'assistant' && Array.isArray(msg.content)) {
                    const textBlock = msg.content.find(block => block.type === 'text');
                    if (textBlock && textBlock.type === 'text') {
                        finalResponse = textBlock.text;
                        break;
                    }
                }
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
        return `Investigate: "Why does this code exist?"

**Target:**
- File: ${this.config.filePath}
- Lines: ${this.config.lineStart}-${this.config.lineEnd}
- Branch: ${this.config.branch || 'HEAD'}
- Local repo: ${this.config.repoPath}

**Goal:** Answer the question efficiently in 3-5 iterations. Focus on quality over exhaustive exploration.

**Recommended Approach:**

1. **Start with get_local_line_context** (often sufficient):
   - owner: "${this.config.owner}"
   - repo: "${this.config.repo}"
   - file_path: "${this.config.filePath}"
   - line_start: ${this.config.lineStart}
   - line_end: ${this.config.lineEnd}
   - ref: "${this.config.branch}"
   - history_depth: 5-10 (use higher for older code)
   - include_discussions: true

2. **If needed, use follow-up tools**:
   - get_pr / get_issue: Get details on linked PRs/issues
   - get_commit_diff: See what changed in a commit
   - trace_symbol_history: Track how a function/class evolved
   - get_file_at_commit: See code at a specific point in time
   - Any other CTM tool that helps answer "why"

3. **Provide your answer** (2-4 paragraphs):
   - What the code does
   - Why it was added (the problem it solves)
   - Key context from commits/PRs/issues
   - Any relevant technical details

**Best Practices:**
- get_local_line_context typically provides everything needed
- Use batch operations when fetching multiple items
- Prefer targeted tools (get_commit_diff) over broad ones (get_github_file)
- Answer the question rather than exploring the entire codebase

You have access to all CTM tools - use them wisely to provide a thorough answer efficiently.`;
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
        const MAX_ARRAY_ITEMS = 5; // Max items to keep from arrays

        if (typeof result !== 'object' || result === null) {
            const str = JSON.stringify(result);
            return str.length > MAX_CONTENT_LENGTH
                ? str.substring(0, MAX_CONTENT_LENGTH) + '... [truncated]'
                : str;
        }

        const truncated: any = {};

        // Handle get_local_line_context and get_line_context specially
        if (toolName === 'get_local_line_context' || toolName === 'get_line_context') {
            // Keep essential fields, truncate large ones
            if (result.line_content) truncated.line_content = result.line_content;
            if (result.file_path) truncated.file_path = result.file_path;
            if (result.line_start) truncated.line_start = result.line_start;
            if (result.line_end) truncated.line_end = result.line_end;

            // Truncate blame commit but keep key info
            if (result.blame_commit) {
                truncated.blame_commit = {
                    sha: result.blame_commit.sha,
                    author: result.blame_commit.author,
                    date: result.blame_commit.date,
                    message: this.truncateString(result.blame_commit.message, 500)
                };
            }

            // Keep PR/issue summaries but truncate
            if (result.pull_request) {
                truncated.pull_request = {
                    number: result.pull_request.number,
                    title: result.pull_request.title,
                    state: result.pull_request.state,
                    body: this.truncateString(result.pull_request.body, 1000)
                };
            }

            if (result.linked_issues && Array.isArray(result.linked_issues)) {
                truncated.linked_issues = result.linked_issues.slice(0, 3).map((issue: any) => ({
                    number: issue.number,
                    title: issue.title,
                    body: this.truncateString(issue.body, 500)
                }));
            }

            // Historical commits - keep limited count
            if (result.historical_commits && Array.isArray(result.historical_commits)) {
                truncated.historical_commits = result.historical_commits.slice(0, 3).map((commit: any) => ({
                    sha: commit.sha,
                    author: commit.author,
                    date: commit.date,
                    message: this.truncateString(commit.message, 300)
                }));
            }

            if (result.context_availability_score !== undefined) {
                truncated.context_availability_score = result.context_availability_score;
            }

            return JSON.stringify(truncated);
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

        // For commit history tools, limit array size
        if (toolName === 'get_github_file_history' || toolName === 'trace_file_history') {
            if (result.commits && Array.isArray(result.commits)) {
                truncated.commits = result.commits.slice(0, MAX_ARRAY_ITEMS).map((c: any) => ({
                    sha: c.sha,
                    author: c.author,
                    date: c.date,
                    message: this.truncateString(c.message, 200)
                }));
                if (result.commits.length > MAX_ARRAY_ITEMS) {
                    truncated.commits_truncated = `Showing ${MAX_ARRAY_ITEMS} of ${result.commits.length} commits`;
                }
            }
            return JSON.stringify(truncated);
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
