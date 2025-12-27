import * as vscode from 'vscode';
import { MCPClient } from './mcpClient';
import { CTMAgent, ProgressUpdate, InvestigationResult } from './agent';
import { ContextPanel, ProgressCallback, StreamCallback } from './ui/contextPanel';
import { detectGitHubRepo, getRelativePath } from './utils/github';
import { DEFAULT_MODEL, DEFAULT_PROVIDER, DEFAULT_MAX_TOOL_CALLS } from './constants';

let mcpClient: MCPClient | null = null;

// Track panels and their associated agents for multi-tab support
const panelData = new Map<ContextPanel, { agent: CTMAgent; summary: string }>();

export async function activate(context: vscode.ExtensionContext) {
    console.log('Codebase Time Machine extension activated');

    // Initialize MCP client
    mcpClient = new MCPClient();

    // Register command
    const command = vscode.commands.registerCommand(
        'ctm.whyDoesThisExist',
        async () => await handleWhyDoesThisExist(context)
    );

    context.subscriptions.push(command);

    // Cleanup on deactivation
    context.subscriptions.push({
        dispose: async () => {
            if (mcpClient) {
                await mcpClient.disconnect();
            }
        }
    });
}

async function handleWhyDoesThisExist(context: vscode.ExtensionContext): Promise<void> {
    console.log('[CTM] ========== Starting Code Context Analysis ==========');
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        console.log('[CTM] ERROR: No active editor');
        vscode.window.showErrorMessage('No active editor');
        return;
    }

    const selection = editor.selection;
    if (selection.isEmpty) {
        console.log('[CTM] WARNING: No code selected');
        vscode.window.showWarningMessage('Please select some code first');
        return;
    }

    // Calculate line numbers (1-indexed)
    // VS Code's selection is 0-indexed
    const startLine = selection.start.line + 1;

    // If selection ends at the beginning of a line (column 0), don't include that line
    // This happens when you select full lines - the cursor ends at the start of the next line
    let endLine = selection.end.line + 1;
    if (selection.end.character === 0 && selection.end.line > selection.start.line) {
        endLine = selection.end.line; // Don't add 1, use the previous line
    }

    console.log('[CTM] Selected lines:', startLine, '-', endLine);
    console.log('[CTM] Selection details:', {
        start: { line: selection.start.line, char: selection.start.character },
        end: { line: selection.end.line, char: selection.end.character }
    });

    const selectedText = editor.document.getText(selection);
    console.log('[CTM] Selected text:');
    console.log(selectedText);

    try {
        // Show progress
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "Analyzing code context...",
            cancellable: false
        }, async (progress) => {
            // Step 1: Detect GitHub repo
            progress.report({ increment: 10, message: "Detecting repository..." });
            console.log('[CTM] Step 1: Detecting GitHub repository');
            let repoInfo;
            try {
                repoInfo = await detectGitHubRepo();
                console.log('[CTM] Repository detected:', repoInfo.owner + '/' + repoInfo.repo);
            } catch (error) {
                console.log('[CTM] ERROR: Cannot detect GitHub repo:', error);
                throw new Error(`Cannot detect GitHub repo: ${error instanceof Error ? error.message : String(error)}`);
            }

            // Step 2: Get file path relative to git root
            progress.report({ increment: 20, message: "Getting file path..." });
            const filePath = getRelativePath(editor.document.fileName, repoInfo.rootPath);
            console.log('[CTM] Step 2: File path (relative to git root):', filePath);

            // Create a new panel for this analysis (supports multiple tabs)
            const lineRange = startLine === endLine ? `${startLine}` : `${startLine}-${endLine}`;
            const fileName = filePath.split('/').pop() || filePath;
            const panel = new ContextPanel();
            panel.showLoading(filePath, lineRange, `${fileName}:${lineRange}`);

            // Step 2.5: Check for uncommitted changes
            progress.report({ increment: 25, message: "Checking for uncommitted changes..." });
            console.log('[CTM] Step 2.5: Checking if file has uncommitted changes');
            const { exec } = require('child_process');
            const { promisify } = require('util');
            const execAsync = promisify(exec);

            let hasUncommittedChanges = false;
            try {
                const { stdout } = await execAsync(`git diff HEAD -- "${filePath}"`, { cwd: repoInfo.rootPath });
                hasUncommittedChanges = stdout.trim().length > 0;
                console.log('[CTM] File has uncommitted changes:', hasUncommittedChanges);

                if (hasUncommittedChanges) {
                    console.log('[CTM] WARNING: File has uncommitted changes. Line numbers may not match git history.');
                    const answer = await vscode.window.showWarningMessage(
                        'This file has uncommitted changes. Git blame will show the last committed version, which may have different line numbers. Do you want to continue?',
                        'Continue Anyway',
                        'Cancel'
                    );
                    if (answer !== 'Continue Anyway') {
                        console.log('[CTM] User cancelled due to uncommitted changes');
                        return;
                    }
                }
            } catch (error) {
                console.log('[CTM] Could not check for uncommitted changes:', error);
                // Continue anyway - this is not a critical error
            }

            // Step 2.6: Detect current branch
            let currentBranch = 'unknown';
            try {
                const { stdout } = await execAsync('git rev-parse --abbrev-ref HEAD', { cwd: repoInfo.rootPath });
                currentBranch = stdout.trim();
                console.log('[CTM] Current branch:', currentBranch);
                console.log('[CTM] NOTE: Analysis will be based on the history of this branch');
            } catch (error) {
                console.log('[CTM] Could not detect current branch:', error);
            }

            // Step 3: Connect to MCP server
            progress.report({ increment: 30, message: "Connecting to CTM server..." });
            console.log('[CTM] Step 3: Connecting to MCP server');
            if (!mcpClient) {
                throw new Error('MCP client not initialized');
            }

            if (!mcpClient.isConnected()) {
                try {
                    await mcpClient.connect();
                    console.log('[CTM] MCP server connection established');
                } catch (error) {
                    console.log('[CTM] ERROR: Failed to connect to MCP server:', error);
                    throw new Error(`Failed to start CTM server. Make sure 'uv' is installed and CTM is set up. Error: ${error instanceof Error ? error.message : String(error)}`);
                }
            } else {
                console.log('[CTM] Already connected to MCP server (reusing connection)');
            }

            // Step 4: Get provider, API key, and model
            progress.report({ increment: 40, message: "Checking configuration..." });
            console.log('[CTM] Step 4: Getting provider, API key, and model');
            const config = vscode.workspace.getConfiguration('ctm');
            const provider = config.get<string>('provider', DEFAULT_PROVIDER);
            // Support both new 'apiKey' and legacy 'anthropicApiKey' for backward compatibility
            const apiKey = config.get<string>('apiKey', '') || config.get<string>('anthropicApiKey', '');
            if (!apiKey) {
                throw new Error('API key not configured. Please set it in VS Code settings (ctm.apiKey)');
            }
            const model = config.get<string>('model', DEFAULT_MODEL);
            const maxToolCalls = config.get<number>('maxToolCalls', DEFAULT_MAX_TOOL_CALLS);
            console.log('[CTM] Using provider:', provider);
            console.log('[CTM] Using model:', model);
            console.log('[CTM] Max tool calls:', maxToolCalls);

            // Step 5: Run agent investigation
            progress.report({ increment: 50, message: "Starting agent investigation..." });
            console.log('[CTM] Step 5: Launching CTM agent');
            const agent = new CTMAgent(mcpClient, {
                provider: provider,
                apiKey: apiKey,
                model: model,
                maxToolCalls: maxToolCalls,
                owner: repoInfo.owner,
                repo: repoInfo.repo,
                repoPath: repoInfo.rootPath,
                filePath: filePath,
                lineStart: startLine,
                lineEnd: endLine,
                branch: currentBranch,
                selectedText: selectedText
            });

            // Set up progress callback for real-time updates
            let lastPercentage = 50;
            agent.setProgressCallback((update: ProgressUpdate) => {
                // Calculate increment from last percentage
                const increment = Math.max(0, update.percentage - lastPercentage);
                lastPercentage = update.percentage;

                // Update progress notification with dynamic message
                progress.report({
                    increment: increment * 0.4, // Scale to fit within our progress range (50-90%)
                    message: update.message
                });

                // Also update the panel's loading progress
                panel.updateProgress(update.message, update.percentage, update.currentTool);
            });

            let summary;
            let rawContext;
            let result: InvestigationResult;
            try {
                result = await agent.investigate();
                summary = result.summary;
                rawContext = result.rawContext;
                console.log('[CTM] Agent investigation complete');
                console.log('[CTM] Summary length:', summary.length, 'characters');
                console.log('[CTM] Completion reason:', result.completionReason);
                console.log('[CTM] Context quality:', result.contextQuality);
                console.groupCollapsed('[CTM] 📦 Collected Context (click to expand)');
                console.log(JSON.stringify(rawContext, null, 2));
                console.groupEnd();
            } catch (error) {
                console.error('[CTM] ERROR: Agent investigation failed:', error);
                throw new Error(`Agent investigation failed: ${error instanceof Error ? error.message : String(error)}`);
            }

            // Step 6: Show in panel
            progress.report({ increment: 90, message: "Displaying results..." });
            console.log('[CTM] Step 6: Displaying results in panel');

            // Add file location to context if missing
            if (!rawContext.file_path) {
                rawContext.file_path = filePath;
            }
            if (!rawContext.line_range && !rawContext.line_start) {
                rawContext.line_start = startLine;
                rawContext.line_end = endLine;
            }

            // Store agent and summary for this panel's follow-up questions
            panelData.set(panel, { agent, summary });

            // Clean up when panel is disposed
            panel.onDispose(() => {
                panelData.delete(panel);
                console.log('[CTM] Panel disposed, removed from tracking');
            });

            // Set up follow-up handler with streaming support
            panel.setFollowUpHandler(async (question: string, onProgress: ProgressCallback, onStream: StreamCallback) => {
                const data = panelData.get(panel);
                if (!data) {
                    throw new Error('No active investigation to follow up on');
                }
                console.log('[CTM] Processing follow-up question:', question);

                // Set up agent progress callback to forward to panel
                data.agent.setProgressCallback((update: ProgressUpdate) => {
                    onProgress(update.message, update.percentage);
                });

                // Pass streaming callback to agent
                return await data.agent.askFollowUp(question, data.summary, onStream);
            });

            panel.show(summary, rawContext, context.extensionUri, `${fileName}:${lineRange}`);

            progress.report({ increment: 100, message: "Done!" });
            console.log('[CTM] ========== Analysis Complete ==========');
        });

    } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(`CTM Error: ${errorMessage}`);
        console.error('CTM Extension Error:', error);
    }
}

export function deactivate() {
    if (mcpClient) {
        mcpClient.disconnect();
    }
}
