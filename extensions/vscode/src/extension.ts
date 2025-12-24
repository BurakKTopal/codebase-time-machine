import * as vscode from 'vscode';
import { MCPClient } from './mcpClient';
import { LLMClient } from './llmClient';
import { ContextPanel } from './ui/contextPanel';
import { detectGitHubRepo } from './utils/github';

let mcpClient: MCPClient | null = null;

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
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor');
        return;
    }

    const selection = editor.selection;
    if (selection.isEmpty) {
        vscode.window.showWarningMessage('Please select some code first');
        return;
    }

    try {
        // Show progress
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "Analyzing code context...",
            cancellable: false
        }, async (progress) => {
            // Step 1: Detect GitHub repo
            progress.report({ increment: 10, message: "Detecting repository..." });
            let repoInfo;
            try {
                repoInfo = await detectGitHubRepo();
            } catch (error) {
                throw new Error(`Cannot detect GitHub repo: ${error instanceof Error ? error.message : String(error)}`);
            }

            // Step 2: Get file path relative to workspace
            progress.report({ increment: 20, message: "Getting file path..." });
            const filePath = vscode.workspace.asRelativePath(editor.document.fileName);

            // Step 3: Connect to MCP server
            progress.report({ increment: 30, message: "Connecting to CTM server..." });
            if (!mcpClient) {
                throw new Error('MCP client not initialized');
            }

            if (!mcpClient.isConnected()) {
                try {
                    await mcpClient.connect();
                } catch (error) {
                    throw new Error(`Failed to start CTM server. Make sure 'uv' is installed and CTM is set up. Error: ${error instanceof Error ? error.message : String(error)}`);
                }
            }

            // Step 4: Get context from MCP server
            progress.report({ increment: 40, message: "Fetching context from MCP server..." });
            let rawContext;
            try {
                rawContext = await mcpClient.getLineContext({
                    owner: repoInfo.owner,
                    repo: repoInfo.repo,
                    file_path: filePath,
                    line_start: selection.start.line + 1,
                    line_end: selection.end.line + 1
                });
            } catch (error) {
                throw new Error(`Failed to get context: ${error instanceof Error ? error.message : String(error)}`);
            }

            // Step 5: Summarize with LLM
            progress.report({ increment: 50, message: "Generating AI summary..." });
            const llmClient = new LLMClient();
            let summary;
            try {
                summary = await llmClient.summarize(rawContext);
            } catch (error) {
                console.error('Error summarizing with LLM:', error);
                summary = 'Error generating summary. See raw context below.';
            }

            // Step 6: Show in panel
            progress.report({ increment: 90, message: "Displaying results..." });
            const panel = new ContextPanel();
            panel.show(summary, rawContext, context.extensionUri);

            progress.report({ increment: 100, message: "Done!" });
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
