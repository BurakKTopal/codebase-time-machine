/**
 * Shared type definitions for CTM VSCode Extension
 */

/**
 * Streaming callback - called with each text chunk during streaming
 */
export type StreamingCallback = (text: string) => void;

/**
 * Configuration for CTM Agent
 */
export interface AgentConfig {
    provider: string;           // Provider ID: 'anthropic', 'openai', 'gemini', etc.
    apiKey: string;
    model: string;              // Model ID from the provider
    maxToolCalls: number;       // Maximum tool calls allowed during investigation
    owner: string;
    repo: string;
    repoPath: string;
    filePath: string;
    lineStart: number;
    lineEnd: number;
    branch?: string;
    selectedText: string;       // The actual text content the user selected
    onStream?: StreamingCallback;  // Optional: for real-time streaming responses
}

/**
 * Progress update for UI feedback
 */
export interface ProgressUpdate {
    phase: AgentPhase;
    toolCallCount: number;
    maxToolCalls: number;
    currentTool?: string;
    message: string;
    percentage: number;
}

/**
 * Agent phase during investigation
 */
export type AgentPhase = 'investigate' | 'synthesize' | 'complete';

/**
 * Callback for progress updates
 */
export type ProgressCallback = (update: ProgressUpdate) => void;

/**
 * Investigation result with metadata
 */
export interface InvestigationResult {
    summary: string;
    rawContext: any;
    completionReason: 'natural' | 'limit_reached' | 'threshold_reached';
    contextQuality: 'high' | 'medium' | 'low';
    toolCallsUsed: number;
    toolsUsed: string[];
    tokensUsed: number;
}
