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
        const maxIterations = 20;
        let finalResponse = '';
        let collectedContext: any = {};

        while (iteration < maxIterations) {
            iteration++;
            console.log(`[CTM Agent] Iteration ${iteration}/${maxIterations}`);

            const messages: Anthropic.MessageParam[] = [
                ...this.conversationHistory,
                iteration === 1 ? { role: 'user', content: initialPrompt } : { role: 'user', content: 'Continue your investigation.' }
            ];

            console.log('[CTM Agent] Calling Claude with', tools.length, 'tools available');

            const response = await this.anthropic.messages.create({
                model: 'claude-sonnet-4-5-20250929',
                max_tokens: 4000,
                tools: tools,
                messages: messages
            });

            console.log('[CTM Agent] Response stop_reason:', response.stop_reason);
            console.log('[CTM Agent] Response usage:', response.usage);

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

                        // Store context if it's get_line_context
                        if (toolUse.name === 'get_line_context') {
                            collectedContext = { ...collectedContext, ...result };
                        }

                        console.log('[CTM Agent] Tool result keys:', Object.keys(result));

                        toolResults.push({
                            type: 'tool_result',
                            tool_use_id: toolUse.id,
                            content: JSON.stringify(result)
                        });
                    }
                }

                // Add tool results to history
                this.conversationHistory.push({
                    role: 'user',
                    content: toolResults
                });
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

        return {
            summary: finalResponse || 'Investigation completed but no summary was generated.',
            rawContext: collectedContext
        };
    }

    private buildInitialPrompt(): string {
        return `You are a code archaeology expert investigating why specific code exists. Your goal is to answer: "Why does this code exist?"

**Investigation Target:**
- Repository: ${this.config.owner}/${this.config.repo}
- Local Path: ${this.config.repoPath}
- File: ${this.config.filePath}
- Lines: ${this.config.lineStart}-${this.config.lineEnd}
- Branch: ${this.config.branch || 'unknown'} (analyzing history from THIS branch)

**CRITICAL - Analyzing LOCAL Code (Not GitHub):**

You are analyzing the user's LOCAL repository files. The code you see is what's on their machine RIGHT NOW - it may have uncommitted or unpushed changes that don't exist on GitHub yet.

**TWO Types of Tools - When to Use Each:**

1. **Local Git Tools** (PREFERRED for code analysis):
   - Tools: \`get_local_line_context\`, \`get_commit_diff\`, \`trace_file_history\`, \`get_file_at_commit\`, \`blame_with_context\`
   - Parameters: Can use EITHER GitHub params OR local params (auto-translated)
   - **IMPORTANT**: When calling \`get_local_line_context\`, ALWAYS pass \`ref: "${this.config.branch}"\` to analyze the correct branch
   - Why prefer: Shows actual local code state, includes uncommitted changes in context
   - **Use for**: Analyzing code content, diffs, file history, symbol tracking

2. **GitHub API Tools** (for social context only):
   - Tools: \`get_pr\`, \`get_issue\`, \`get_github_repo\`, \`get_code_context\`
   - Parameters: \`owner\`, \`repo\`
   - Why use: Access PRs, issues, discussions (not available locally)
   - **Use for**: Understanding WHY decisions were made (PRs, issues)

**Your Investigation Process:**

1. **Start with LOCAL tools**: Use \`get_local_line_context\` as PRIMARY tool (analyzes local files).

2. **Follow the Speed Hierarchy**:
   - ⚡ INSTANT (<1s): get_file_at_commit (local), get_file_symbols (local)
   - 🚀 FAST (1-5s): get_local_line_context (local), get_commit_diff (local), trace_file_history (local)
   - 🚀 FAST (GitHub): get_pr, get_issue, get_github_commit (for PR/issue context)
   - 🐌 SLOW (5-15s): get_code_context (GitHub), trace_symbol_history (local)
   - 🐢 VERY SLOW (15-30s): search_github_code (LAST RESORT)

3. **Key Principles**:
   - Start with get_local_line_context (analyzes actual local code with history_depth=5-10)
   - Use local tools for code/diffs: get_commit_diff, trace_file_history, get_file_at_commit
   - Use GitHub tools for context: get_pr, get_issue (when commit is linked to them)
   - Parameters auto-translate: you can use owner/repo params even for local tools
   - Only go deeper if initial results don't answer the question
   - Aim to complete in 3-5 tool calls maximum

4. **Your Final Answer Should**:
   - Explain WHAT the code does
   - Explain WHY it was added (the problem it solves)
   - Include context from commits, PRs, issues
   - Note any technical considerations or trade-offs
   - Be factual and objective (no conversational language)
   - Be 2-4 paragraphs

**Start your investigation now. Use get_local_line_context first to analyze the local code state.**`;
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
