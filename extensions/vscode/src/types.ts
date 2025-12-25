/**
 * Shared type definitions for CTM VSCode Extension
 */

/**
 * Configuration for CTM Agent
 */
export interface AgentConfig {
    apiKey: string;
    owner: string;
    repo: string;
    repoPath: string;
    filePath: string;
    lineStart: number;
    lineEnd: number;
    branch?: string;
    model: string;  // Claude model to use
    selectedText: string;  // The actual text content the user selected
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
 * Investigation result with metadata for continue functionality
 */
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

/**
 * State preserved for continuation
 */
export interface InvestigationState {
    summary: string;
    toolsUsed: string[];
    rawContext: any;
    toolCallsUsed: number;
    tokensUsed: number;
}
