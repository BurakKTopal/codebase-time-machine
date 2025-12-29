/**
 * Anthropic Claude Provider Implementation
 */

import Anthropic from '@anthropic-ai/sdk';
import {
    ILLMProvider,
    LLMRequestConfig,
    LLMResponse,
    LLMModel,
    LLMContentBlock,
    LLMTextBlock,
    LLMToolUseBlock,
    ProviderConfig,
    StreamCallback,
    LLMTool
} from './types';

/**
 * Available Claude models
 */
export const CLAUDE_MODELS: LLMModel[] = [
    {
        id: 'claude-3-5-haiku-20241022',
        label: 'Haiku 3.5',
        description: 'Fast, cheapest ($0.80/$4)',
        contextWindow: 200000
    },
    {
        id: 'claude-haiku-4-5-20251001',
        label: 'Haiku 4.5',
        description: 'Fast, cheap ($1/$5)',
        contextWindow: 200000
    },
    {
        id: 'claude-sonnet-4-5-20250929',
        label: 'Sonnet 4.5',
        description: 'Balanced ($3/$15)',
        contextWindow: 200000
    }
    // Opus 4.5 disabled - too expensive for most users ($15/$75)
    // {
    //     id: 'claude-opus-4-5-20251101',
    //     label: 'Opus 4.5',
    //     description: 'Most capable ($15/$75)',
    //     contextWindow: 200000
    // }
];

/**
 * Anthropic Claude Provider
 */
export class AnthropicProvider implements ILLMProvider {
    readonly name = 'anthropic';
    readonly displayName = 'Anthropic Claude';
    private client: Anthropic;

    constructor(config: ProviderConfig) {
        this.client = new Anthropic({
            apiKey: config.apiKey,
            dangerouslyAllowBrowser: true
        });
    }

    /**
     * Create a message (non-streaming)
     */
    async createMessage(config: LLMRequestConfig): Promise<LLMResponse> {
        const anthropicMessages = this.convertMessages(config.messages);
        const anthropicTools = config.tools ? this.convertTools(config.tools) : undefined;

        const response = await this.client.messages.create({
            model: config.model,
            max_tokens: config.maxTokens,
            system: config.systemPrompt,
            messages: anthropicMessages,
            tools: anthropicTools
        });

        return this.convertResponse(response);
    }

    /**
     * Create a message with streaming support
     */
    async createMessageStream(
        config: LLMRequestConfig,
        onChunk: StreamCallback
    ): Promise<LLMResponse> {
        const anthropicMessages = this.convertMessages(config.messages);
        const anthropicTools = config.tools ? this.convertTools(config.tools) : undefined;

        // Accumulated content for final response
        const contentBlocks: LLMContentBlock[] = [];
        let currentTextBlock: LLMTextBlock | null = null;
        let currentToolBlock: LLMToolUseBlock | null = null;
        let toolInputJson = '';
        let inputTokens = 0;
        let outputTokens = 0;
        let stopReason: string = 'end_turn';

        const stream = await this.client.messages.stream({
            model: config.model,
            max_tokens: config.maxTokens,
            system: config.systemPrompt,
            messages: anthropicMessages,
            tools: anthropicTools
        });

        for await (const event of stream) {
            switch (event.type) {
                case 'message_start':
                    if (event.message?.usage) {
                        inputTokens = event.message.usage.input_tokens;
                    }
                    break;

                case 'content_block_start':
                    if (event.content_block?.type === 'text') {
                        currentTextBlock = { type: 'text', text: '' };
                    } else if (event.content_block?.type === 'tool_use') {
                        currentToolBlock = {
                            type: 'tool_use',
                            id: event.content_block.id,
                            name: event.content_block.name,
                            input: {}
                        };
                        toolInputJson = '';
                        onChunk({
                            type: 'tool_use_start',
                            id: event.content_block.id,
                            name: event.content_block.name
                        });
                    }
                    break;

                case 'content_block_delta':
                    if (event.delta?.type === 'text_delta' && currentTextBlock) {
                        currentTextBlock.text += event.delta.text;
                        onChunk({ type: 'text_delta', text: event.delta.text });
                    } else if (event.delta?.type === 'input_json_delta' && currentToolBlock) {
                        toolInputJson += event.delta.partial_json;
                        onChunk({ type: 'tool_use_delta', partialInput: event.delta.partial_json });
                    }
                    break;

                case 'content_block_stop':
                    if (currentTextBlock) {
                        contentBlocks.push(currentTextBlock);
                        currentTextBlock = null;
                    } else if (currentToolBlock) {
                        // Parse accumulated JSON input
                        try {
                            currentToolBlock.input = toolInputJson ? JSON.parse(toolInputJson) : {};
                        } catch {
                            currentToolBlock.input = {};
                        }
                        contentBlocks.push(currentToolBlock);
                        currentToolBlock = null;
                        toolInputJson = '';
                    }
                    break;

                case 'message_delta':
                    if (event.delta?.stop_reason) {
                        stopReason = event.delta.stop_reason;
                    }
                    if (event.usage?.output_tokens) {
                        outputTokens = event.usage.output_tokens;
                    }
                    break;

                case 'message_stop':
                    onChunk({
                        type: 'done',
                        usage: { inputTokens, outputTokens },
                        stopReason: this.mapStopReason(stopReason)
                    });
                    break;
            }
        }

        return {
            content: contentBlocks,
            usage: { inputTokens, outputTokens },
            stopReason: this.mapStopReason(stopReason)
        };
    }

    /**
     * Get available models for this provider
     */
    getAvailableModels(): LLMModel[] {
        return CLAUDE_MODELS;
    }

    /**
     * Convert our message format to Anthropic's format
     */
    private convertMessages(messages: LLMRequestConfig['messages']): Anthropic.MessageParam[] {
        return messages
            .filter(m => m.role !== 'system') // System is passed separately
            .map(message => {
                if (typeof message.content === 'string') {
                    return {
                        role: message.role as 'user' | 'assistant',
                        content: message.content
                    };
                }

                // Convert content blocks
                const anthropicContent = message.content.map(block => {
                    switch (block.type) {
                        case 'text':
                            return { type: 'text' as const, text: block.text };
                        case 'tool_use':
                            return {
                                type: 'tool_use' as const,
                                id: block.id,
                                name: block.name,
                                input: block.input
                            };
                        case 'tool_result':
                            return {
                                type: 'tool_result' as const,
                                tool_use_id: block.tool_use_id,
                                content: block.content
                            };
                        default:
                            throw new Error(`Unknown block type: ${(block as any).type}`);
                    }
                });

                return {
                    role: message.role as 'user' | 'assistant',
                    content: anthropicContent
                };
            });
    }

    /**
     * Convert our tool format to Anthropic's format
     */
    private convertTools(tools: LLMTool[]): Anthropic.Tool[] {
        return tools.map(tool => ({
            name: tool.name,
            description: tool.description,
            input_schema: tool.inputSchema as Anthropic.Tool.InputSchema
        }));
    }

    /**
     * Convert Anthropic response to our format
     */
    private convertResponse(response: Anthropic.Message): LLMResponse {
        const content: LLMContentBlock[] = response.content.map(block => {
            if (block.type === 'text') {
                return { type: 'text' as const, text: block.text };
            } else if (block.type === 'tool_use') {
                return {
                    type: 'tool_use' as const,
                    id: block.id,
                    name: block.name,
                    input: block.input as Record<string, unknown>
                };
            }
            throw new Error(`Unknown Anthropic block type: ${(block as any).type}`);
        });

        return {
            content,
            usage: {
                inputTokens: response.usage.input_tokens,
                outputTokens: response.usage.output_tokens
            },
            stopReason: this.mapStopReason(response.stop_reason)
        };
    }

    /**
     * Map Anthropic stop reason to our format
     */
    private mapStopReason(reason: string | null): string {
        if (!reason) return 'end_turn';

        const mapping: Record<string, string> = {
            'end_turn': 'end_turn',
            'tool_use': 'tool_use',
            'max_tokens': 'max_tokens',
            'stop_sequence': 'stop_sequence'
        };

        return mapping[reason] || reason;
    }
}
