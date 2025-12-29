/**
 * Google Gemini Provider Implementation
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
 * Available Gemini models
 */
export const GEMINI_MODELS: LLMModel[] = [
    {
        id: 'gemini-2.0-flash-lite',
        label: 'Gemini 2.0 Flash-Lite',
        description: 'Fastest, cheapest ($0.075/$0.30)',
        contextWindow: 1000000
    },
    {
        id: 'gemini-2.5-flash',
        label: 'Gemini 2.5 Flash',
        description: 'Balanced with thinking ($0.15/$0.60)',
        contextWindow: 1000000
    }
    // Gemini Pro disabled - expensive
    // {
    //     id: 'gemini-2.5-pro',
    //     label: 'Gemini 2.5 Pro',
    //     description: 'Most powerful',
    //     contextWindow: 2000000
    // }
];

/**
 * Google Gemini Provider
 */
export class GeminiProvider implements ILLMProvider {
    readonly name = 'gemini';
    readonly displayName = 'Google Gemini';
    private apiKey: string;
    private baseUrl: string;

    constructor(config: ProviderConfig) {
        this.apiKey = config.apiKey;
        this.baseUrl = config.baseUrl || 'https://generativelanguage.googleapis.com/v1beta';
    }

    /**
     * Create a message (non-streaming)
     */
    async createMessage(config: LLMRequestConfig): Promise<LLMResponse> {
        const geminiContents = this.convertMessages(config.messages);
        const geminiTools = config.tools ? this.convertTools(config.tools) : undefined;

        const requestBody: any = {
            contents: geminiContents,
            generationConfig: {
                maxOutputTokens: config.maxTokens
            }
        };

        if (config.systemPrompt) {
            requestBody.systemInstruction = {
                parts: [{ text: config.systemPrompt }]
            };
        }

        if (geminiTools && geminiTools.length > 0) {
            requestBody.tools = [{ functionDeclarations: geminiTools }];
        }

        const url = `${this.baseUrl}/models/${config.model}:generateContent?key=${this.apiKey}`;

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const error = await response.text();
            throw new Error(`Gemini API error: ${response.status} ${error}`);
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
        const geminiContents = this.convertMessages(config.messages);
        const geminiTools = config.tools ? this.convertTools(config.tools) : undefined;

        const requestBody: any = {
            contents: geminiContents,
            generationConfig: {
                maxOutputTokens: config.maxTokens
            }
        };

        if (config.systemPrompt) {
            requestBody.systemInstruction = {
                parts: [{ text: config.systemPrompt }]
            };
        }

        if (geminiTools && geminiTools.length > 0) {
            requestBody.tools = [{ functionDeclarations: geminiTools }];
        }

        const url = `${this.baseUrl}/models/${config.model}:streamGenerateContent?key=${this.apiKey}&alt=sse`;

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const error = await response.text();
            throw new Error(`Gemini API error: ${response.status} ${error}`);
        }

        // Accumulated content for final response
        const contentBlocks: LLMContentBlock[] = [];
        let currentText = '';
        const toolCalls: { id: string; name: string; args: any }[] = [];
        let finishReason = 'STOP';
        let promptTokens = 0;
        let completionTokens = 0;

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) {
            throw new Error('No response body');
        }

        try {
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6).trim();
                        if (!data) continue;

                        try {
                            const parsed = JSON.parse(data);
                            const candidate = parsed.candidates?.[0];

                            if (candidate?.finishReason) {
                                finishReason = candidate.finishReason;
                            }

                            if (parsed.usageMetadata) {
                                promptTokens = parsed.usageMetadata.promptTokenCount || 0;
                                completionTokens = parsed.usageMetadata.candidatesTokenCount || 0;
                            }

                            const parts = candidate?.content?.parts;
                            if (parts) {
                                for (const part of parts) {
                                    if (part.text) {
                                        currentText += part.text;
                                        onChunk({ type: 'text_delta', text: part.text });
                                    }
                                    if (part.functionCall) {
                                        const tc = {
                                            id: `call_${toolCalls.length}`,
                                            name: part.functionCall.name,
                                            args: part.functionCall.args || {}
                                        };
                                        toolCalls.push(tc);
                                        onChunk({
                                            type: 'tool_use_start',
                                            id: tc.id,
                                            name: tc.name
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

        for (const tc of toolCalls) {
            contentBlocks.push({
                type: 'tool_use',
                id: tc.id,
                name: tc.name,
                input: tc.args
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
        return GEMINI_MODELS;
    }

    /**
     * Convert our message format to Gemini's format
     */
    private convertMessages(messages: LLMRequestConfig['messages']): any[] {
        const geminiContents: any[] = [];

        for (const message of messages) {
            const role = message.role === 'assistant' ? 'model' : 'user';

            if (typeof message.content === 'string') {
                geminiContents.push({
                    role,
                    parts: [{ text: message.content }]
                });
            } else {
                const parts: any[] = [];

                for (const block of message.content) {
                    switch (block.type) {
                        case 'text':
                            parts.push({ text: block.text });
                            break;
                        case 'tool_use':
                            parts.push({
                                functionCall: {
                                    name: block.name,
                                    args: block.input
                                }
                            });
                            break;
                        case 'tool_result':
                            parts.push({
                                functionResponse: {
                                    name: block.tool_use_id,
                                    response: {
                                        content: block.content
                                    }
                                }
                            });
                            break;
                    }
                }

                if (parts.length > 0) {
                    geminiContents.push({ role, parts });
                }
            }
        }

        return geminiContents;
    }

    /**
     * Convert our tool format to Gemini's format
     */
    private convertTools(tools: LLMTool[]): any[] {
        return tools.map(tool => {
            // Gemini expects a slightly different schema format
            const parameters = { ...tool.inputSchema } as any;

            // Ensure type is 'object' for Gemini
            if (!parameters.type) {
                parameters.type = 'object';
            }

            return {
                name: tool.name,
                description: tool.description,
                parameters
            };
        });
    }

    /**
     * Convert Gemini response to our format
     */
    private convertResponse(response: any): LLMResponse {
        const candidate = response.candidates?.[0];
        const content: LLMContentBlock[] = [];

        const parts = candidate?.content?.parts || [];
        for (const part of parts) {
            if (part.text) {
                content.push({ type: 'text', text: part.text });
            }
            if (part.functionCall) {
                content.push({
                    type: 'tool_use',
                    id: `call_${content.filter(c => c.type === 'tool_use').length}`,
                    name: part.functionCall.name,
                    input: part.functionCall.args || {}
                });
            }
        }

        return {
            content,
            usage: {
                inputTokens: response.usageMetadata?.promptTokenCount || 0,
                outputTokens: response.usageMetadata?.candidatesTokenCount || 0
            },
            stopReason: this.mapFinishReason(candidate?.finishReason)
        };
    }

    /**
     * Map Gemini finish reason to our format
     */
    private mapFinishReason(reason: string | null): string {
        if (!reason) return 'end_turn';

        const mapping: Record<string, string> = {
            'STOP': 'end_turn',
            'MAX_TOKENS': 'max_tokens',
            'SAFETY': 'end_turn',
            'RECITATION': 'end_turn',
            'OTHER': 'end_turn'
        };

        return mapping[reason] || reason;
    }
}
