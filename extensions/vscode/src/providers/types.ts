/**
 * Provider Interface Types for CTM VSCode Extension
 *
 * This abstraction allows switching between AI providers (Anthropic, OpenAI, Gemini, etc.)
 */

/**
 * Message role for conversation
 */
export type MessageRole = 'user' | 'assistant' | 'system';

/**
 * Content block types in messages
 */
export interface LLMTextBlock {
    type: 'text';
    text: string;
}

export interface LLMToolUseBlock {
    type: 'tool_use';
    id: string;
    name: string;
    input: Record<string, unknown>;
}

export interface LLMToolResultBlock {
    type: 'tool_result';
    tool_use_id: string;
    content: string;
}

export type LLMContentBlock = LLMTextBlock | LLMToolUseBlock | LLMToolResultBlock;

/**
 * Message in a conversation
 */
export interface LLMMessage {
    role: MessageRole;
    content: string | LLMContentBlock[];
}

/**
 * Tool definition for the LLM
 */
export interface LLMTool {
    name: string;
    description: string;
    inputSchema: Record<string, unknown>;
}

/**
 * Token usage information
 */
export interface LLMUsage {
    inputTokens: number;
    outputTokens: number;
}

/**
 * Stop reason for generation
 */
export type LLMStopReason = 'end_turn' | 'tool_use' | 'max_tokens' | 'stop_sequence' | string;

/**
 * Response from the LLM
 */
export interface LLMResponse {
    content: LLMContentBlock[];
    usage: LLMUsage;
    stopReason: LLMStopReason;
}

/**
 * Request configuration for creating a message
 */
export interface LLMRequestConfig {
    model: string;
    messages: LLMMessage[];
    systemPrompt?: string;
    tools?: LLMTool[];
    maxTokens: number;
}

/**
 * Model information
 */
export interface LLMModel {
    id: string;
    label: string;
    description: string;
    contextWindow?: number;
}

/**
 * Streaming chunk types
 */
export interface LLMStreamChunkText {
    type: 'text_delta';
    text: string;
}

export interface LLMStreamChunkToolStart {
    type: 'tool_use_start';
    id: string;
    name: string;
}

export interface LLMStreamChunkToolDelta {
    type: 'tool_use_delta';
    partialInput: string;
}

export interface LLMStreamChunkDone {
    type: 'done';
    usage: LLMUsage;
    stopReason: LLMStopReason;
}

export type LLMStreamChunk =
    | LLMStreamChunkText
    | LLMStreamChunkToolStart
    | LLMStreamChunkToolDelta
    | LLMStreamChunkDone;

/**
 * Callback for streaming responses
 */
export type StreamCallback = (chunk: LLMStreamChunk) => void;

/**
 * Configuration for a provider
 */
export interface ProviderConfig {
    apiKey: string;
    baseUrl?: string;  // For custom endpoints (Ollama, Azure, etc.)
}

/**
 * Main provider interface - all providers must implement this
 */
export interface ILLMProvider {
    /**
     * Provider identifier (e.g., 'anthropic', 'openai', 'gemini')
     */
    readonly name: string;

    /**
     * Human-readable display name
     */
    readonly displayName: string;

    /**
     * Create a message (non-streaming)
     */
    createMessage(config: LLMRequestConfig): Promise<LLMResponse>;

    /**
     * Create a message with streaming support
     * Calls onChunk for each delta, returns final accumulated response
     */
    createMessageStream(
        config: LLMRequestConfig,
        onChunk: StreamCallback
    ): Promise<LLMResponse>;

    /**
     * Get available models for this provider
     */
    getAvailableModels(): LLMModel[];
}
