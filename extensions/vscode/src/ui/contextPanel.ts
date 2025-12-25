import * as vscode from 'vscode';
import { InvestigationResult } from '../agent';

export type ProgressCallback = (message: string, percentage: number) => void;
export type FollowUpHandler = (question: string, onProgress: ProgressCallback) => Promise<string>;
export type ContinueHandler = (onProgress: ProgressCallback) => Promise<InvestigationResult>;

export class ContextPanel {
    private panel: vscode.WebviewPanel | undefined;
    private onFollowUp: FollowUpHandler | undefined;
    private onContinue: ContinueHandler | undefined;
    private conversationHistory: Array<{ role: 'user' | 'assistant'; content: string }> = [];
    private canContinue: boolean = false;

    /**
     * Set the handler for follow-up questions
     */
    setFollowUpHandler(handler: FollowUpHandler): void {
        this.onFollowUp = handler;
    }

    /**
     * Set the handler for continue investigation
     */
    setContinueHandler(handler: ContinueHandler): void {
        this.onContinue = handler;
    }

    show(summary: string, rawContext: any, _extensionUri: vscode.Uri, canContinue: boolean = false): void {
        this.canContinue = canContinue;
        // Reset conversation history for new investigation
        this.conversationHistory = [];

        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.Beside);
        } else {
            this.panel = vscode.window.createWebviewPanel(
                'ctmContext',
                'Code Context',
                vscode.ViewColumn.Beside,
                {
                    enableScripts: true,
                    retainContextWhenHidden: true
                }
            );

            this.panel.onDidDispose(() => {
                this.panel = undefined;
                this.onFollowUp = undefined;
                this.onContinue = undefined;
            });

            // Set up message handler
            this.panel.webview.onDidReceiveMessage(
                async (message) => {
                    if (message.command === 'followUp' && this.onFollowUp) {
                        const question = message.question;
                        console.log('[ContextPanel] Received follow-up question:', question);

                        // Add user question to history
                        this.conversationHistory.push({ role: 'user', content: question });

                        // Show loading state
                        this.updateConversation(true, 'Processing question...', 10);

                        try {
                            // Progress callback to update loading message
                            const onProgress: ProgressCallback = (progressMessage, percentage) => {
                                this.updateConversation(true, progressMessage, percentage);
                            };

                            // Get answer from agent with progress updates
                            const answer = await this.onFollowUp(question, onProgress);

                            // Add answer to history
                            this.conversationHistory.push({ role: 'assistant', content: answer });

                            // Update UI
                            this.updateConversation(false);
                        } catch (error) {
                            console.error('[ContextPanel] Follow-up error:', error);
                            const errorMsg = error instanceof Error ? error.message : String(error);
                            this.conversationHistory.push({
                                role: 'assistant',
                                content: `Error: ${errorMsg}`
                            });
                            this.updateConversation(false);
                        }
                    }

                    // Handle continue investigation
                    if (message.command === 'continueInvestigation' && this.onContinue) {
                        console.log('[ContextPanel] Received continue investigation request');

                        // Hide the continue button and show progress
                        this.panel?.webview.postMessage({ command: 'hideContinueButton' });
                        this.updateConversation(true, 'Continuing investigation...', 5);

                        try {
                            const onProgress: ProgressCallback = (progressMessage, percentage) => {
                                this.updateConversation(true, progressMessage, percentage);
                            };

                            const result = await this.onContinue(onProgress);

                            // Add the new summary to conversation
                            this.conversationHistory.push({
                                role: 'assistant',
                                content: result.summary
                            });

                            // Update canContinue based on new result
                            this.canContinue = result.canContinue;

                            // Update UI
                            this.updateConversation(false);

                            // Show continue button again if still can continue
                            if (result.canContinue) {
                                this.panel?.webview.postMessage({ command: 'showContinueButton' });
                            }
                        } catch (error) {
                            console.error('[ContextPanel] Continue error:', error);
                            const errorMsg = error instanceof Error ? error.message : String(error);
                            this.conversationHistory.push({
                                role: 'assistant',
                                content: `Error continuing investigation: ${errorMsg}`
                            });
                            this.updateConversation(false);
                        }
                    }
                }
            );
        }

        this.panel.webview.html = this.getHtmlContent(summary, rawContext);
    }

    /**
     * Update the conversation section without rebuilding the entire panel
     */
    private updateConversation(isLoading: boolean, loadingMessage?: string, percentage?: number): void {
        if (!this.panel) return;

        // Send message to webview to update conversation
        this.panel.webview.postMessage({
            command: 'updateConversation',
            history: this.conversationHistory,
            isLoading: isLoading,
            loadingMessage: loadingMessage || 'Investigating...',
            percentage: percentage || 0
        });
    }

    private getHtmlContent(summary: string, context: any): string {
        // Convert markdown-like summary to HTML
        const htmlSummary = this.convertMarkdownToHtml(summary);

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Context</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--vscode-foreground);
            background: var(--vscode-editor-background);
            padding: 20px;
            line-height: 1.6;
        }
        h1, h2, h3, h4 {
            color: var(--vscode-foreground);
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }
        h1 { font-size: 1.8em; border-bottom: 2px solid var(--vscode-panel-border); padding-bottom: 0.3em; }
        h2 { font-size: 1.5em; }
        h3 { font-size: 1.3em; }
        h4 { font-size: 1.1em; }
        .summary {
            background: var(--vscode-textBlockQuote-background);
            border-left: 4px solid var(--vscode-textLink-foreground);
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .section {
            margin: 20px 0;
            padding: 15px;
            background: var(--vscode-editor-background);
            border-radius: 4px;
        }
        .commit {
            border-left: 3px solid #4CAF50;
            padding-left: 15px;
            margin: 10px 0;
        }
        .pr {
            border-left: 3px solid #2196F3;
            padding-left: 15px;
            margin: 10px 0;
        }
        .issue {
            border-left: 3px solid #FF9800;
            padding-left: 15px;
            margin: 10px 0;
        }
        .warning {
            background: var(--vscode-inputValidation-warningBackground);
            border: 1px solid var(--vscode-inputValidation-warningBorder);
            padding: 12px;
            margin: 15px 0;
            border-radius: 4px;
        }
        .info {
            background: var(--vscode-inputValidation-infoBackground);
            border: 1px solid var(--vscode-inputValidation-infoBorder);
            padding: 12px;
            margin: 15px 0;
            border-radius: 4px;
        }
        a {
            color: var(--vscode-textLink-foreground);
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        code {
            background: var(--vscode-textCodeBlock-background);
            padding: 2px 6px;
            border-radius: 3px;
            font-family: var(--vscode-editor-font-family);
        }
        pre {
            background: var(--vscode-textCodeBlock-background);
            padding: 12px;
            border-radius: 4px;
            overflow-x: auto;
        }
        .metadata {
            color: var(--vscode-descriptionForeground);
            font-size: 0.9em;
        }
        blockquote {
            border-left: 4px solid var(--vscode-panel-border);
            padding-left: 15px;
            margin: 10px 0;
            color: var(--vscode-descriptionForeground);
            font-style: italic;
        }
        ul, ol {
            margin: 10px 0;
            padding-left: 30px;
        }
        li {
            margin: 5px 0;
        }
        .follow-up-section {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid var(--vscode-panel-border);
        }
        .follow-up-section h2 {
            margin-bottom: 15px;
        }
        #conversation {
            max-height: 400px;
            overflow-y: auto;
            margin-bottom: 15px;
        }
        .message {
            margin-bottom: 12px;
            padding: 10px 12px;
            border-radius: 6px;
        }
        .user-message {
            background: var(--vscode-input-background);
            border: 1px solid var(--vscode-input-border);
            margin-left: 20px;
        }
        .assistant-message {
            background: var(--vscode-textBlockQuote-background);
            border-left: 3px solid var(--vscode-textLink-foreground);
            margin-right: 20px;
        }
        .message-header {
            font-size: 0.85em;
            font-weight: bold;
            color: var(--vscode-descriptionForeground);
            margin-bottom: 5px;
        }
        .message-content {
            line-height: 1.5;
        }
        .message-content.loading {
            color: var(--vscode-descriptionForeground);
            font-style: italic;
        }
        .loading-text {
            margin-bottom: 8px;
        }
        .progress-bar {
            height: 4px;
            background: var(--vscode-progressBar-background);
            border-radius: 2px;
            overflow: hidden;
            margin-top: 8px;
        }
        .progress-fill {
            height: 100%;
            background: var(--vscode-progressBar-background);
            background: linear-gradient(90deg, var(--vscode-textLink-foreground), var(--vscode-textLink-activeForeground, var(--vscode-textLink-foreground)));
            transition: width 0.3s ease;
        }
        .input-container {
            display: flex;
            gap: 8px;
        }
        #followUpInput {
            flex: 1;
            padding: 8px 12px;
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            font-family: inherit;
            font-size: inherit;
        }
        #followUpInput:focus {
            outline: none;
            border-color: var(--vscode-focusBorder);
        }
        #followUpInput:disabled {
            opacity: 0.6;
        }
        #sendButton {
            padding: 8px 16px;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-family: inherit;
            font-size: inherit;
        }
        #sendButton:hover {
            background: var(--vscode-button-hoverBackground);
        }
        #sendButton:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .continue-section {
            background: var(--vscode-inputValidation-warningBackground);
            border: 1px solid var(--vscode-inputValidation-warningBorder);
            border-radius: 6px;
            padding: 16px;
            margin: 20px 0;
        }
        .continue-section h3 {
            margin: 0 0 8px 0;
            color: var(--vscode-foreground);
        }
        .continue-section p {
            margin: 0 0 12px 0;
            color: var(--vscode-descriptionForeground);
        }
        #continueButton {
            padding: 8px 16px;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-family: inherit;
            font-size: inherit;
        }
        #continueButton:hover {
            background: var(--vscode-button-hoverBackground);
        }
        #continueButton:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <h1>Code Context</h1>

    <div class="summary">
        ${htmlSummary}
    </div>

    <div id="continue-section" class="continue-section" style="display: ${this.canContinue ? 'block' : 'none'};">
        <h3>Investigation Incomplete</h3>
        <p>The agent reached its tool call limit. Some context may be missing.</p>
        <button id="continueButton">Continue Investigating</button>
    </div>

    <div class="section">
        <h2>Location</h2>
        <p><strong>File:</strong> <code>${context.file_path}</code></p>
        <p><strong>Lines:</strong> ${context.line_range || `${context.line_start || '?'}-${context.line_end || '?'}`}</p>
    </div>

    ${context.blame_commit ? `
    <div class="section commit">
        <h2>Last Modified</h2>
        <p><strong>Commit:</strong> <code>${context.blame_commit.sha ? context.blame_commit.sha.slice(0, 7) : 'unknown'}</code></p>
        <p><strong>Author:</strong> ${this.escapeHtml(context.blame_commit.author || 'unknown')}</p>
        <p><strong>Date:</strong> ${context.blame_commit.date || 'unknown'}</p>
        <p><strong>Message:</strong> ${this.escapeHtml(context.blame_commit.message || '')}</p>
    </div>
    ` : ''}

    ${context.pull_request ? `
    <div class="section pr">
        <h2>Pull Request #${context.pull_request.number}</h2>
        <p><strong>${this.escapeHtml(context.pull_request.title)}</strong></p>
        ${context.pull_request.body ? `<p>${this.escapeHtml(context.pull_request.body.slice(0, 300))}${context.pull_request.body.length > 300 ? '...' : ''}</p>` : ''}
        ${context.pull_request.html_url ? `<p><a href="${context.pull_request.html_url}">View on GitHub</a></p>` : ''}
        <p class="metadata">Merged: ${context.pull_request.merged_at ? new Date(context.pull_request.merged_at).toLocaleDateString() : 'Not merged'}</p>
    </div>
    ` : ''}

    ${context.linked_issues && context.linked_issues.length > 0 ? context.linked_issues.map((issue: any) => `
    <div class="section issue">
        <h2>Issue #${issue.number}</h2>
        <p><strong>${this.escapeHtml(issue.title)}</strong></p>
        ${issue.body ? `<p>${this.escapeHtml(issue.body.slice(0, 300))}${issue.body.length > 300 ? '...' : ''}</p>` : ''}
        ${issue.html_url ? `<p><a href="${issue.html_url}">View on GitHub</a></p>` : ''}
        <p class="metadata">State: ${issue.state || 'unknown'}</p>
    </div>
    `).join('') : ''}

    ${context.discussions && context.discussions.length > 0 ? `
    <div class="section">
        <h2>Key Discussions</h2>
        ${context.discussions.slice(0, 3).map((d: any) => `
            <blockquote>
                <p>${this.escapeHtml(d.body ? d.body.slice(0, 200) : '')}${d.body && d.body.length > 200 ? '...' : ''}</p>
                <p class="metadata">— ${this.escapeHtml(d.author || 'unknown')}</p>
            </blockquote>
        `).join('')}
    </div>
    ` : ''}

    ${!context.pull_request && (!context.linked_issues || context.linked_issues.length === 0) ? `
    <div class="info">
        <p><strong>Note:</strong> Limited Context</p>
        <p>This code doesn't have linked PRs or issues. The context is based on Git history only.</p>
    </div>
    ` : ''}

    <div class="follow-up-section">
        <h2>Follow-up Questions</h2>
        <div id="conversation"></div>
        <div class="input-container">
            <input type="text" id="followUpInput" placeholder="Ask a follow-up question..." />
            <button id="sendButton">Send</button>
        </div>
    </div>

    <div class="metadata" style="margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--vscode-panel-border);">
        <p>Powered by <a href="https://github.com/burak/codebase-time-machine">Codebase Time Machine</a></p>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const input = document.getElementById('followUpInput');
        const sendButton = document.getElementById('sendButton');
        const conversation = document.getElementById('conversation');
        const continueSection = document.getElementById('continue-section');
        const continueButton = document.getElementById('continueButton');

        function sendQuestion() {
            const question = input.value.trim();
            if (!question) return;

            // Disable input while processing
            input.disabled = true;
            sendButton.disabled = true;

            // Send to extension
            vscode.postMessage({
                command: 'followUp',
                question: question
            });

            // Clear input
            input.value = '';
        }

        // Send on button click
        sendButton.addEventListener('click', sendQuestion);

        // Send on Enter key
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendQuestion();
            }
        });

        // Continue investigation button
        if (continueButton) {
            continueButton.addEventListener('click', () => {
                continueButton.disabled = true;
                continueButton.textContent = 'Continuing...';
                vscode.postMessage({ command: 'continueInvestigation' });
            });
        }

        // Handle messages from extension
        window.addEventListener('message', (event) => {
            const message = event.data;
            if (message.command === 'updateConversation') {
                updateConversation(message.history, message.isLoading, message.loadingMessage, message.percentage);
            }
            if (message.command === 'hideContinueButton' && continueSection) {
                continueSection.style.display = 'none';
            }
            if (message.command === 'showContinueButton' && continueSection && continueButton) {
                continueSection.style.display = 'block';
                continueButton.disabled = false;
                continueButton.textContent = 'Continue Investigating';
            }
        });

        function updateConversation(history, isLoading, loadingMessage, percentage) {
            let html = '';

            for (const msg of history) {
                const roleClass = msg.role === 'user' ? 'user-message' : 'assistant-message';
                const roleLabel = msg.role === 'user' ? 'You' : 'CTM';
                const content = convertMarkdownToHtml(msg.content);
                html += '<div class="message ' + roleClass + '">';
                html += '<div class="message-header">' + roleLabel + '</div>';
                html += '<div class="message-content">' + content + '</div>';
                html += '</div>';
            }

            if (isLoading) {
                const displayMessage = loadingMessage || 'Investigating...';
                const pct = percentage || 0;
                html += '<div class="message assistant-message">';
                html += '<div class="message-header">CTM</div>';
                html += '<div class="message-content loading">';
                html += '<div class="loading-text">' + displayMessage + '</div>';
                if (pct > 0) {
                    html += '<div class="progress-bar"><div class="progress-fill" style="width: ' + pct + '%"></div></div>';
                }
                html += '</div>';
                html += '</div>';
            }

            conversation.innerHTML = html;

            // Scroll to bottom
            conversation.scrollTop = conversation.scrollHeight;

            // Re-enable input if not loading
            if (!isLoading) {
                input.disabled = false;
                sendButton.disabled = false;
                input.focus();
            }
        }

        function convertMarkdownToHtml(text) {
            if (!text) return '';
            let html = text;
            // Bold
            html = html.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
            // Italic
            html = html.replace(/\\*(.*?)\\*/g, '<em>$1</em>');
            // Code blocks
            html = html.replace(/\`\`\`([\\s\\S]*?)\`\`\`/g, '<pre><code>$1</code></pre>');
            // Inline code
            html = html.replace(/\`([^\`]+)\`/g, '<code>$1</code>');
            // Line breaks
            html = html.replace(/\\n/g, '<br>');
            return html;
        }
    </script>
</body>
</html>`;
    }

    private convertMarkdownToHtml(markdown: string): string {
        let html = markdown;

        // Headers
        html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

        // Bold
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Italic
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

        // Code blocks
        html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');

        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Links
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

        // Lists
        html = html.replace(/^\* (.*$)/gim, '<li>$1</li>');
        html = html.replace(/^\- (.*$)/gim, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

        // Blockquotes
        html = html.replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>');

        // Paragraphs
        html = html.replace(/\n\n/g, '</p><p>');
        if (!html.startsWith('<h') && !html.startsWith('<p>')) {
            html = '<p>' + html;
        }
        if (!html.endsWith('</p>') && !html.endsWith('>')) {
            html = html + '</p>';
        }

        return html;
    }

    private escapeHtml(text: string): string {
        const map: { [key: string]: string } = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
}
