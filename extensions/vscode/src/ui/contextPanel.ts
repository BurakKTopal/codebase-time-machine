import * as vscode from 'vscode';
import { DEFAULT_MODEL, DEFAULT_PROVIDER } from '../constants';
import { getModelsForProvider, LLMModel } from '../providers';

export type ProgressCallback = (message: string, percentage: number) => void;
export type StreamCallback = (chunk: string) => void;
export type FollowUpHandler = (question: string, onProgress: ProgressCallback, onStream: StreamCallback) => Promise<string>;

export class ContextPanel {
    private panel: vscode.WebviewPanel | undefined;
    private onFollowUp: FollowUpHandler | undefined;
    private conversationHistory: Array<{ role: 'user' | 'assistant'; content: string }> = [];
    private messageHandlerDisposable: vscode.Disposable | undefined;
    private disposeCallbacks: Array<() => void> = [];

    /**
     * Set the handler for follow-up questions
     */
    setFollowUpHandler(handler: FollowUpHandler): void {
        this.onFollowUp = handler;
    }

    /**
     * Register a callback to be called when the panel is disposed
     */
    onDispose(callback: () => void): void {
        this.disposeCallbacks.push(callback);
    }

    /**
     * Show the panel in loading state (before investigation completes)
     */
    showLoading(filePath: string, lineRange: string, title?: string): void {
        this.conversationHistory = [];

        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.Beside);
        } else {
            this.panel = vscode.window.createWebviewPanel(
                'ctmContext',
                title ? `CTM: ${title}` : 'Code Context',
                vscode.ViewColumn.Beside,
                {
                    enableScripts: true,
                    retainContextWhenHidden: true
                }
            );

            this.panel.onDidDispose(() => {
                this.panel = undefined;
                this.onFollowUp = undefined;
                // Call all registered dispose callbacks
                this.disposeCallbacks.forEach(cb => cb());
                this.disposeCallbacks = [];
            });
        }

        this.panel.webview.html = this.getLoadingHtml(filePath, lineRange);
    }

    /**
     * Update the loading progress
     */
    updateProgress(message: string, percentage: number, currentTool?: string): void {
        if (!this.panel) return;

        this.panel.webview.postMessage({
            command: 'updateProgress',
            message,
            percentage,
            currentTool
        });
    }

    show(summary: string, rawContext: any, _extensionUri: vscode.Uri, title?: string): void {
        // Reset conversation history for new investigation
        this.conversationHistory = [];

        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.Beside);
            // Update title if provided
            if (title) {
                this.panel.title = `CTM: ${title}`;
            }
        } else {
            this.panel = vscode.window.createWebviewPanel(
                'ctmContext',
                title ? `CTM: ${title}` : 'Code Context',
                vscode.ViewColumn.Beside,
                {
                    enableScripts: true,
                    retainContextWhenHidden: true
                }
            );

            this.panel.onDidDispose(() => {
                this.panel = undefined;
                this.onFollowUp = undefined;
                this.messageHandlerDisposable = undefined;
                // Call all registered dispose callbacks
                this.disposeCallbacks.forEach(cb => cb());
                this.disposeCallbacks = [];
            });
        }

        // Always set up message handler (dispose old one first)
        this.setupMessageHandler();

        this.panel.webview.html = this.getHtmlContent(summary, rawContext);
    }

    /**
     * Set up the webview message handler for follow-up questions
     */
    private setupMessageHandler(): void {
        if (!this.panel) return;

        // Dispose old handler if exists
        if (this.messageHandlerDisposable) {
            this.messageHandlerDisposable.dispose();
        }

        this.messageHandlerDisposable = this.panel.webview.onDidReceiveMessage(
            async (message) => {
                // Handle /model command
                if (message.command === 'changeModel') {
                    console.log('[ContextPanel] Received change model request');
                    await this.handleModelChange();
                    return;
                }

                if (message.command === 'followUp' && this.onFollowUp) {
                    const question = message.question;
                    console.log('[ContextPanel] Received follow-up question:', question);

                    // Check for /model command
                    if (question.trim().toLowerCase() === '/model') {
                        await this.handleModelChange();
                        return;
                    }

                    // Add user question to history
                    this.conversationHistory.push({ role: 'user', content: question });

                    // Add empty assistant message for streaming
                    this.conversationHistory.push({ role: 'assistant', content: '' });
                    const assistantMsgIndex = this.conversationHistory.length - 1;

                    // Show initial state
                    this.updateConversation(true, 'Processing question...', 10);

                    try {
                        // Progress callback to update loading message
                        const onProgress: ProgressCallback = (progressMessage, percentage) => {
                            this.updateConversation(true, progressMessage, percentage);
                        };

                        // Streaming callback to update response in real-time
                        const onStream: StreamCallback = (chunk: string) => {
                            this.conversationHistory[assistantMsgIndex].content += chunk;
                            this.streamToConversation(chunk);
                        };

                        // Get answer from agent with progress and streaming
                        const answer = await this.onFollowUp(question, onProgress, onStream);

                        // Ensure final answer is in history (in case streaming didn't capture all)
                        this.conversationHistory[assistantMsgIndex].content = answer;

                        // Update UI (removes loading state)
                        this.updateConversation(false);
                    } catch (error) {
                        console.error('[ContextPanel] Follow-up error:', error);
                        const errorMsg = error instanceof Error ? error.message : String(error);
                        this.conversationHistory[assistantMsgIndex].content = `Error: ${errorMsg}`;
                        this.updateConversation(false);
                    }
                }
            }
        );
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

    /**
     * Stream a chunk of text to the conversation (for real-time updates)
     */
    private streamToConversation(chunk: string): void {
        if (!this.panel) return;

        this.panel.webview.postMessage({
            command: 'streamChunk',
            chunk: chunk
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
        :root {
            --ctm-brand: #F97316;
            --ctm-brand-dark: #E86305;
            --ctm-brand-light: #FB923C;
        }
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
        h1 { font-size: 1.8em; border-bottom: 2px solid var(--vscode-panel-border); padding-bottom: 0.3em; display: flex; align-items: center; gap: 12px; }
        .logo {
            width: 36px;
            height: 36px;
            flex-shrink: 0;
        }
        h2 { font-size: 1.5em; }
        h3 { font-size: 1.3em; }
        h4 { font-size: 1.1em; }
        .summary {
            background: var(--vscode-textBlockQuote-background);
            border-left: 4px solid var(--ctm-brand);
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
            border-left: 3px solid #22c55e;
            padding-left: 15px;
            margin: 10px 0;
        }
        .issue {
            border-left: 3px solid #a855f7;
            padding-left: 15px;
            margin: 10px 0;
        }
        .location {
            border-left: 3px solid var(--ctm-brand);
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
            color: var(--ctm-brand);
            text-decoration: none;
        }
        a:hover {
            color: var(--ctm-brand-light);
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
            border-left: 3px solid var(--ctm-brand);
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
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
            overflow: hidden;
            margin-top: 8px;
        }
        .progress-fill {
            height: 100%;
            background: var(--ctm-brand);
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
            border-color: var(--ctm-brand);
        }
        #followUpInput:disabled {
            opacity: 0.6;
        }
        #sendButton {
            padding: 8px 16px;
            background: var(--ctm-brand);
            color: #ffffff;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-family: inherit;
            font-size: inherit;
            font-weight: 500;
        }
        #sendButton:hover {
            background: var(--ctm-brand-dark);
        }
        #sendButton:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .spinner-arrow {
            display: inline-block;
            width: 16px;
            height: 16px;
            margin-right: 6px;
            vertical-align: middle;
            animation: spin 1.2s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(-360deg); }
        }
    </style>
</head>
<body>
    <h1>
        <svg class="logo" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
            <rect width="128" height="128" rx="16" fill="#1e1e1e"/>
            <g transform="translate(13, 0)">
                <path d="M40 32 L20 64 L40 96" stroke="#ffffff" stroke-width="4" fill="none" stroke-linecap="round"/>
                <path d="M25 32 L5 64 L25 96" stroke="#ffffff" stroke-width="4" fill="none" stroke-linecap="round"/>
                <path d="M50 43 A24 24 0 1 1 76 84" stroke="#F97316" stroke-width="3" fill="none" stroke-linecap="round"/>
                <circle cx="62" cy="64" r="3" fill="#F97316"/>
                <path d="M58 46 L50 43" stroke="#F97316" stroke-width="3" stroke-linecap="round"/>
                <path d="M54 35 L50 43" stroke="#F97316" stroke-width="3" stroke-linecap="round"/>
                <path d="M97 32 L97 96" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/>
            </g>
        </svg>
        Code Context
    </h1>

    <div class="summary">
        ${htmlSummary}
    </div>

    <div class="section location">
        <h2>Location</h2>
        <p><strong>File:</strong> <code>${context.file_path}</code></p>
        <p><strong>Lines:</strong> ${context.line_start === context.line_end ? context.line_start : (context.line_range || `${context.line_start || '?'}-${context.line_end || '?'}`)}</p>
    </div>

    ${context.blame_commits && context.blame_commits.length > 1 ? `
    <div class="section commit">
        <h2>Last Touched <span class="metadata">(${context.blame_commits.length} commits)</span></h2>
        <p class="metadata" style="margin-top: -10px; margin-bottom: 15px;">These commits last modified the selected lines. For true origin, see the summary above.</p>
        ${context.blame_commits.map((bc: any) => `
        <div class="blame-commit">
            <p><strong>Commit:</strong> ${bc.html_url
                ? `<a href="${bc.html_url}"><code>${bc.sha ? bc.sha.slice(0, 7) : 'unknown'}</code></a>`
                : `<code>${bc.sha ? bc.sha.slice(0, 7) : 'unknown'}</code>`
            }</p>
            <p><strong>Author:</strong> ${this.escapeHtml(bc.author || 'unknown')}</p>
            <p><strong>Date:</strong> ${bc.date || 'unknown'}</p>
            <p><strong>Message:</strong> ${this.escapeHtml(bc.message || '')}</p>
            ${bc.lines ? `<p class="metadata">Lines: ${bc.lines.join(', ')}</p>` : ''}
            ${bc.html_url ? `<p><a href="${bc.html_url}">View Commit →</a></p>` : ''}
        </div>
        `).join('<hr style="margin: 10px 0; border: none; border-top: 1px solid var(--vscode-panel-border);">')}
    </div>
    ` : context.blame_commit ? `
    <div class="section commit">
        <h2>Last Touched</h2>
        <p class="metadata" style="margin-top: -10px; margin-bottom: 15px;">This commit last modified the selected lines. For true origin, see the summary above.</p>
        <p><strong>Commit:</strong> ${context.blame_commit.html_url
            ? `<a href="${context.blame_commit.html_url}"><code>${context.blame_commit.sha ? context.blame_commit.sha.slice(0, 7) : 'unknown'}</code></a>`
            : `<code>${context.blame_commit.sha ? context.blame_commit.sha.slice(0, 7) : 'unknown'}</code>`
        }</p>
        <p><strong>Author:</strong> ${this.escapeHtml(context.blame_commit.author || 'unknown')}</p>
        <p><strong>Date:</strong> ${context.blame_commit.date || 'unknown'}</p>
        <p><strong>Message:</strong> ${this.escapeHtml(context.blame_commit.message || '')}</p>
        ${context.blame_commit.html_url ? `<p><a href="${context.blame_commit.html_url}">View Commit →</a></p>` : ''}
    </div>
    ` : ''}

    ${context.pull_request && context.pull_request.number ? `
    <div class="section pr">
        <h2>${context.pull_request.html_url
            ? `<a href="${context.pull_request.html_url}">Pull Request #${context.pull_request.number}</a>`
            : `Pull Request #${context.pull_request.number}`
        } <span class="metadata">(last touched)</span></h2>
        ${context.pull_request.title
            ? `<p><strong>${context.pull_request.html_url
                ? `<a href="${context.pull_request.html_url}">${this.escapeHtml(context.pull_request.title)}</a>`
                : this.escapeHtml(context.pull_request.title)
            }</strong></p>`
            : context.pull_request.html_url
                ? `<p><a href="${context.pull_request.html_url}">View PR →</a></p>`
                : ''
        }
        ${context.pull_request.author ? `<p class="metadata">By: ${this.escapeHtml(context.pull_request.author)}</p>` : ''}
        ${context.pull_request.body ? `<p>${this.escapeHtml(context.pull_request.body.slice(0, 300))}${context.pull_request.body.length > 300 ? '...' : ''}</p>` : ''}
        <p class="metadata">State: ${context.pull_request.state ?
            (context.pull_request.state === 'merged' ? `✓ Merged${context.pull_request.merged_at ? ' on ' + new Date(context.pull_request.merged_at).toLocaleDateString() : ''}` :
             context.pull_request.state === 'closed' ? '✗ Closed (not merged)' :
             context.pull_request.state === 'open' ? '○ Open' :
             this.escapeHtml(context.pull_request.state))
        : 'Unknown'}</p>
    </div>
    ` : ''}

    ${context.linked_issues && context.linked_issues.length > 0 ? context.linked_issues.filter((issue: any) => issue && issue.number).map((issue: any) => `
    <div class="section issue">
        <h2>${issue.html_url
            ? `<a href="${issue.html_url}">Issue #${issue.number}</a>`
            : `Issue #${issue.number}`
        }</h2>
        ${issue.title
            ? `<p><strong>${issue.html_url
                ? `<a href="${issue.html_url}">${this.escapeHtml(issue.title)}</a>`
                : this.escapeHtml(issue.title)
            }</strong></p>`
            : issue.html_url
                ? `<p><a href="${issue.html_url}">View Issue →</a></p>`
                : ''
        }
        ${issue.author ? `<p class="metadata">By: ${this.escapeHtml(issue.author)}</p>` : ''}
        ${issue.body ? `<p>${this.escapeHtml(issue.body.slice(0, 300))}${issue.body.length > 300 ? '...' : ''}</p>` : ''}
        <p class="metadata">State: ${issue.state ?
            (issue.state === 'closed' ? '✓ Closed' :
             issue.state === 'open' ? '○ Open' :
             this.escapeHtml(issue.state))
        : 'Unknown'}</p>
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

    ${(!context.pull_request || !context.pull_request.number) && (!context.linked_issues || context.linked_issues.length === 0) ? `
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
        <p>Powered by <a href="https://github.com/BurakKTopal/codebase-time-machine">Codebase Time Machine</a></p>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const input = document.getElementById('followUpInput');
        const sendButton = document.getElementById('sendButton');
        const conversation = document.getElementById('conversation');

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

        // Track streaming state
        let streamingContent = '';
        let streamingElement = null;

        // Handle messages from extension
        window.addEventListener('message', (event) => {
            const message = event.data;
            if (message.command === 'updateConversation') {
                // Reset streaming state when conversation updates
                streamingContent = '';
                streamingElement = null;
                updateConversation(message.history, message.isLoading, message.loadingMessage, message.percentage);
            }
            if (message.command === 'streamChunk') {
                handleStreamChunk(message.chunk);
            }
        });

        function handleStreamChunk(chunk) {
            streamingContent += chunk;

            // Find or create the streaming message element
            if (!streamingElement) {
                // Look for the last assistant message (should be empty placeholder)
                const messages = conversation.querySelectorAll('.assistant-message');
                if (messages.length > 0) {
                    streamingElement = messages[messages.length - 1].querySelector('.message-content');
                }
            }

            if (streamingElement) {
                // Update with accumulated content (convert markdown)
                streamingElement.innerHTML = convertMarkdownToHtml(streamingContent);
                // Scroll to bottom
                conversation.scrollTop = conversation.scrollHeight;
            }
        }

        function updateConversation(history, isLoading, loadingMessage, percentage) {
            let html = '';

            for (let i = 0; i < history.length; i++) {
                const msg = history[i];
                const isLastMessage = i === history.length - 1;

                // Skip empty assistant messages when loading - the loading block will show instead
                if (isLoading && isLastMessage && msg.role === 'assistant' && !msg.content) {
                    continue;
                }

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
                const spinnerSvg = '<svg class="spinner-arrow" viewBox="0 0 50 50"><path d="M13 8 A17 17 0 1 1 31 38" stroke="#F97316" stroke-width="4" fill="none" stroke-linecap="round"/><path d="M18 11 L13 8" stroke="#F97316" stroke-width="4" stroke-linecap="round"/><path d="M16 3 L13 8" stroke="#F97316" stroke-width="4" stroke-linecap="round"/></svg>';
                html += '<div class="message assistant-message">';
                html += '<div class="message-header">CTM</div>';
                html += '<div class="message-content">';
                html += '<div class="loading-text">' + spinnerSvg + displayMessage + '</div>';
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
            // Headers
            html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
            html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
            html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
            // Bold
            html = html.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
            // Italic
            html = html.replace(/\\*(.*?)\\*/g, '<em>$1</em>');
            // Code blocks
            html = html.replace(/\`\`\`([\\s\\S]*?)\`\`\`/g, '<pre><code>$1</code></pre>');
            // Inline code
            html = html.replace(/\`([^\`]+)\`/g, '<code>$1</code>');
            // Links - IMPORTANT for clickable commits/PRs/issues
            html = html.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="$2" target="_blank">$1</a>');
            // Line breaks
            html = html.replace(/\\n/g, '<br>');
            return html;
        }
    </script>
</body>
</html>`;
    }

    private convertMarkdownToHtml(markdown: string): string {
        // First, escape HTML entities to prevent XSS and broken HTML
        // This ensures literal < and > in the summary don't break the page
        let html = markdown
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

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
        html = html.replace(/^- (.*$)/gim, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

        // Blockquotes
        html = html.replace(/^&gt; (.*$)/gim, '<blockquote>$1</blockquote>');

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

    /**
     * Handle /model command - show quick pick to change model
     */
    private async handleModelChange(): Promise<void> {
        const config = vscode.workspace.getConfiguration('ctm');
        const currentModel = config.get<string>('model', DEFAULT_MODEL);
        const currentProvider = config.get<string>('provider', DEFAULT_PROVIDER);

        // Get models for current provider
        const availableModels = getModelsForProvider(currentProvider);

        // Build quick pick items
        const items = availableModels.map((model: LLMModel) => ({
            label: model.label,
            description: model.description,
            detail: model.id === currentModel ? '$(check) Current model' : undefined,
            id: model.id
        }));

        const selected = await vscode.window.showQuickPick(items, {
            placeHolder: 'Select model for code analysis',
            title: 'Change Model'
        });

        if (selected) {
            // Update the setting
            await config.update('model', selected.id, vscode.ConfigurationTarget.Global);

            // Show confirmation in conversation
            this.conversationHistory.push({
                role: 'user',
                content: '/model'
            });
            this.conversationHistory.push({
                role: 'assistant',
                content: `Model changed to **${selected.label}** (${selected.description}). The new model will be used for the next investigation.`
            });
            this.updateConversation(false);

            vscode.window.showInformationMessage(`CTM: Model changed to ${selected.label}`);
        } else {
            // User cancelled - re-enable input
            this.updateConversation(false);
        }
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

    /**
     * Generate HTML for the loading state
     */
    private getLoadingHtml(filePath: string, lineRange: string): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Context - Loading</title>
    <style>
        :root {
            --ctm-brand: #F97316;
            --ctm-brand-dark: #E86305;
            --ctm-brand-light: #FB923C;
        }
        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--vscode-foreground);
            background: var(--vscode-editor-background);
            padding: 20px;
            line-height: 1.6;
        }
        h1 {
            font-size: 1.8em;
            border-bottom: 2px solid var(--vscode-panel-border);
            padding-bottom: 0.3em;
            margin-bottom: 1em;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .logo {
            width: 36px;
            height: 36px;
            flex-shrink: 0;
        }
        .loading-container {
            background: var(--vscode-textBlockQuote-background);
            border-left: 4px solid var(--ctm-brand);
            padding: 20px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .file-info {
            margin-bottom: 20px;
        }
        .file-info code {
            background: var(--vscode-textCodeBlock-background);
            padding: 2px 6px;
            border-radius: 3px;
            font-family: var(--vscode-editor-font-family);
        }
        .progress-section {
            margin-top: 20px;
        }
        .progress-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        .progress-message {
            color: var(--vscode-foreground);
        }
        .progress-percentage {
            color: var(--vscode-descriptionForeground);
            font-weight: bold;
        }
        .progress-bar-container {
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            overflow: hidden;
        }
        .progress-bar-fill {
            height: 100%;
            background: var(--ctm-brand);
            transition: width 0.3s ease;
            border-radius: 4px;
        }
        .current-tool {
            margin-top: 12px;
            color: var(--vscode-descriptionForeground);
            font-size: 0.9em;
        }
        .spinner-arrow {
            display: inline-block;
            width: 18px;
            height: 18px;
            margin-right: 8px;
            vertical-align: middle;
            animation: spin 1.2s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(-360deg); }
        }
        a {
            color: var(--ctm-brand);
            text-decoration: none;
        }
        a:hover {
            color: var(--ctm-brand-light);
        }
        .metadata {
            color: var(--vscode-descriptionForeground);
            font-size: 0.9em;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid var(--vscode-panel-border);
        }
    </style>
</head>
<body>
    <h1>
        <svg class="logo" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
            <rect width="128" height="128" rx="16" fill="#1e1e1e"/>
            <g transform="translate(13, 0)">
                <path d="M40 32 L20 64 L40 96" stroke="#ffffff" stroke-width="4" fill="none" stroke-linecap="round"/>
                <path d="M25 32 L5 64 L25 96" stroke="#ffffff" stroke-width="4" fill="none" stroke-linecap="round"/>
                <path d="M50 43 A24 24 0 1 1 76 84" stroke="#F97316" stroke-width="3" fill="none" stroke-linecap="round"/>
                <circle cx="62" cy="64" r="3" fill="#F97316"/>
                <path d="M58 46 L50 43" stroke="#F97316" stroke-width="3" stroke-linecap="round"/>
                <path d="M54 35 L50 43" stroke="#F97316" stroke-width="3" stroke-linecap="round"/>
                <path d="M97 32 L97 96" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/>
            </g>
        </svg>
        Code Context
    </h1>

    <div class="loading-container">
        <div class="file-info">
            <p><strong>Analyzing:</strong> <code>${this.escapeHtml(filePath)}</code></p>
            <p><strong>Lines:</strong> ${this.escapeHtml(lineRange)}</p>
        </div>

        <div class="progress-section">
            <div class="progress-header">
                <span class="progress-message" id="progressMessage"><svg class="spinner-arrow" viewBox="0 0 50 50"><path d="M13 8 A17 17 0 1 1 31 38" stroke="#F97316" stroke-width="4" fill="none" stroke-linecap="round"/><path d="M18 11 L13 8" stroke="#F97316" stroke-width="4" stroke-linecap="round"/><path d="M16 3 L13 8" stroke="#F97316" stroke-width="4" stroke-linecap="round"/></svg>Starting investigation...</span>
                <span class="progress-percentage" id="progressPercentage">0%</span>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar-fill" id="progressBar" style="width: 0%"></div>
            </div>
            <div class="current-tool" id="currentTool"></div>
        </div>
    </div>

    <div class="metadata">
        <p>Powered by <a href="https://github.com/BurakKTopal/codebase-time-machine">Codebase Time Machine</a></p>
    </div>

    <script>
        const progressMessage = document.getElementById('progressMessage');
        const progressPercentage = document.getElementById('progressPercentage');
        const progressBar = document.getElementById('progressBar');
        const currentTool = document.getElementById('currentTool');

        window.addEventListener('message', (event) => {
            const message = event.data;
            if (message.command === 'updateProgress') {
                // Update progress message with spinning arrow
                progressMessage.innerHTML = '<svg class="spinner-arrow" viewBox="0 0 50 50"><path d="M13 8 A17 17 0 1 1 31 38" stroke="#F97316" stroke-width="4" fill="none" stroke-linecap="round"/><path d="M18 11 L13 8" stroke="#F97316" stroke-width="4" stroke-linecap="round"/><path d="M16 3 L13 8" stroke="#F97316" stroke-width="4" stroke-linecap="round"/></svg>' + message.message;

                // Update percentage
                progressPercentage.textContent = Math.round(message.percentage) + '%';

                // Update progress bar
                progressBar.style.width = message.percentage + '%';

                // Update current tool if provided
                if (message.currentTool) {
                    currentTool.textContent = 'Using: ' + message.currentTool;
                } else {
                    currentTool.textContent = '';
                }
            }
        });
    </script>
</body>
</html>`;
    }
}
