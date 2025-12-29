/**
 * OpenAI Provider Implementation
 */

import {
    ILLMProvider,
    LLMRequestConfig,
    LLMResponse,
    LLMModel,
    LLMContentBlock,
    ProviderConfig,
    StreamCallback,
    LLMTool
} from './types';

/**
 * Available OpenAI models
 */
export const OPENAI_MODELS: LLMModel[] = [
    {
        id: 'gpt-4.1-nano',
        label: 'GPT-4.1 Nano',
        description: 'Fastest, cheapest ($0.10/$0.40)',
        contextWindow: 128000
    },
    {
        id: 'gpt-4.1',
        label: 'GPT-4.1',
        description: 'Balanced, great for coding ($2/$8)',
        contextWindow: 128000
    }
    // o1 disabled - expensive reasoning model
    // {
    //     id: 'o1',
    //     label: 'o1',
    //     description: 'Advanced reasoning',
    //     contextWindow: 200000
    // }
];

/**
 * OpenAI Provider
 */
export class OpenAIProvider implements ILLMProvider {
    readonly name = 'openai';
    readonly displayName = 'OpenAI';
    private apiKey: string;
    private baseUrl: string;

    constructor(config: ProviderConfig) {
        this.apiKey = config.apiKey;
        this.baseUrl = config.baseUrl || 'https://api.openai.com/v1';
    }

    /**
     * Create a message (non-streaming)
     */
    async createMessage(config: LLMRequestConfig): Promise<LLMResponse> {
        const openaiMessages = this.convertMessages(config.messages, config.systemPrompt);
        const openaiTools = config.tools ? this.convertTools(config.tools) : undefined;

        const requestBody: any = {
            model: config.model,
            max_tokens: config.maxTokens,
            messages: openaiMessages
        };

        if (openaiTools && openaiTools.length > 0) {
            requestBody.tools = openaiTools;
        }

        const response = await fetch(`${this.baseUrl}/chat/completions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.apiKey}`
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const error = await response.text();
            throw new Error(`OpenAI API error: ${response.status} ${error}`);
        }

        const data = await response.json();
        return this.convertResponse(data);
    }

    /**
     * Create a message with streaming support
     */
    async createMessageStream(
        config: LLMRequestConfig,
        onChunk: StreamCallback
    ): Promise<LLMResponse> {
        const openaiMessages = this.convertMessages(config.messages, config.systemPrompt);
        const openaiTools = config.tools ? this.convertTools(config.tools) : undefined;

        const requestBody: any = {
            model: config.model,
            max_tokens: config.maxTokens,
            messages: openaiMessages,
            stream: true
        };

        if (openaiTools && openaiTools.length > 0) {
            requestBody.tools = openaiTools;
        }

        const response = await fetch(`${this.baseUrl}/chat/completions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.apiKey}`
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const error = await response.text();
            throw new Error(`OpenAI API error: ${response.status} ${error}`);
        }

        // Accumulated content for final response
        const contentBlocks: LLMContentBlock[] = [];
        let currentText = '';
        const currentToolCalls: Map<number, { id: string; name: string; arguments: string }> = new Map();
        let finishReason = 'stop';
        let promptTokens = 0;
        let completionTokens = 0;

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) {
            throw new Error('No response body');
        }

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n').filter(line => line.trim() !== '');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data === '[DONE]') continue;

                        try {
                            const parsed = JSON.parse(data);
                            const delta = parsed.choices?.[0]?.delta;
                            const choice = parsed.choices?.[0];

                            if (choice?.finish_reason) {
                                finishReason = choice.finish_reason;
                            }

                            if (parsed.usage) {
                                promptTokens = parsed.usage.prompt_tokens || 0;
                                completionTokens = parsed.usage.completion_tokens || 0;
                            }

                            if (delta?.content) {
                                currentText += delta.content;
                                onChunk({ type: 'text_delta', text: delta.content });
                            }

                            if (delta?.tool_calls) {
                                for (const tc of delta.tool_calls) {
                                    const index = tc.index;
                                    if (!currentToolCalls.has(index)) {
                                        currentToolCalls.set(index, {
                                            id: tc.id || '',
                                            name: tc.function?.name || '',
                                            arguments: ''
                                        });
                                        if (tc.function?.name) {
                                            onChunk({
                                                type: 'tool_use_start',
                                                id: tc.id,
                                                name: tc.function.name
                                            });
                                        }
                                    }
                                    const existing = currentToolCalls.get(index)!;
                                    if (tc.id) existing.id = tc.id;
                                    if (tc.function?.name) existing.name = tc.function.name;
                                    if (tc.function?.arguments) {
                                        existing.arguments += tc.function.arguments;
                                        onChunk({
                                            type: 'tool_use_delta',
                                            partialInput: tc.function.arguments
                                        });
                                    }
                                }
                            }
                        } catch {
                            // Skip unparseable lines
                        }
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }

        // Build final content blocks
        if (currentText) {
            contentBlocks.push({ type: 'text', text: currentText });
        }

        for (const tc of currentToolCalls.values()) {
            let parsedArgs = {};
            try {
                parsedArgs = JSON.parse(tc.arguments || '{}');
            } catch {
                parsedArgs = {};
            }
            contentBlocks.push({
                type: 'tool_use',
                id: tc.id,
                name: tc.name,
                input: parsedArgs
            });
        }

        onChunk({
            type: 'done',
            usage: { inputTokens: promptTokens, outputTokens: completionTokens },
            stopReason: this.mapFinishReason(finishReason)
        });

        return {
            content: contentBlocks,
            usage: { inputTokens: promptTokens, outputTokens: completionTokens },
            stopReason: this.mapFinishReason(finishReason)
        };
    }

    /**
     * Get available models for this provider
     */
    getAvailableModels(): LLMModel[] {
        return OPENAI_MODELS;
    }

    /**
     * Convert our message format to OpenAI's format
     */
    private convertMessages(
        messages: LLMRequestConfig['messages'],
        systemPrompt?: string
    ): any[] {
        const openaiMessages: any[] = [];

        // Add system message first if provided
        if (systemPrompt) {
            openaiMessages.push({
                role: 'system',
                content: systemPrompt
            });
        }

        for (const message of messages) {
            if (typeof message.content === 'string') {
                openaiMessages.push({
                    role: message.role,
                    content: message.content
                });
            } else {
                // Handle content blocks
                const parts: any[] = [];
                const toolCalls: any[] = [];
                const toolResults: any[] = [];

                for (const block of message.content) {
                    switch (block.type) {
                        case 'text':
                            parts.push({ type: 'text', text: block.text });
                            break;
                        case 'tool_use':
                            toolCalls.push({
                                id: block.id,
                                type: 'function',
                                function: {
                                    name: block.name,
                                    arguments: JSON.stringify(block.input)
                                }
                            });
                            break;
                        case 'tool_result':
                            toolResults.push({
                                role: 'tool',
                                tool_call_id: block.tool_use_id,
                                content: block.content
                            });
                            break;
                    }
                }

                if (parts.length > 0) {
                    openaiMessages.push({
                        role: message.role,
                        content: parts.length === 1 && parts[0].type === 'text'
                            ? parts[0].text
                            : parts
                    });
                }

                if (toolCalls.length > 0) {
                    openaiMessages.push({
                        role: 'assistant',
                        tool_calls: toolCalls
                    });
                }

                for (const result of toolResults) {
                    openaiMessages.push(result);
                }
            }
        }

        return openaiMessages;
    }

    /**
     * Convert our tool format to OpenAI's format
     */
    private convertTools(tools: LLMTool[]): any[] {
        return tools.map(tool => ({
            type: 'function',
            function: {
                name: tool.name,
                description: tool.description,
                parameters: tool.inputSchema
            }
        }));
    }

    /**
     * Convert OpenAI response to our format
     */
    private convertResponse(response: any): LLMResponse {
        const choice = response.choices?.[0];
        const message = choice?.message;
        const content: LLMContentBlock[] = [];

        if (message?.content) {
            content.push({ type: 'text', text: message.content });
        }

        if (message?.tool_calls) {
            for (const tc of message.tool_calls) {
                let parsedArgs = {};
                try {
                    parsedArgs = JSON.parse(tc.function?.arguments || '{}');
                } catch {
                    parsedArgs = {};
                }
                content.push({
                    type: 'tool_use',
                    id: tc.id,
                    name: tc.function?.name || '',
                    input: parsedArgs
                });
            }
        }

        return {
            content,
            usage: {
                inputTokens: response.usage?.prompt_tokens || 0,
                outputTokens: response.usage?.completion_tokens || 0
            },
            stopReason: this.mapFinishReason(choice?.finish_reason)
        };
    }

    /**
     * Map OpenAI finish reason to our format
     */
    private mapFinishReason(reason: string | null): string {
        if (!reason) return 'end_turn';

        const mapping: Record<string, string> = {
            'stop': 'end_turn',
            'tool_calls': 'tool_use',
            'length': 'max_tokens',
            'content_filter': 'end_turn'
        };

        return mapping[reason] || reason;
    }
}
