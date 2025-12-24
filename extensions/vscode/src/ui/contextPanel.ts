import * as vscode from 'vscode';

export class ContextPanel {
    private panel: vscode.WebviewPanel | undefined;

    show(summary: string, rawContext: any, extensionUri: vscode.Uri): void {
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
            });
        }

        this.panel.webview.html = this.getHtmlContent(summary, rawContext);
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
    </style>
</head>
<body>
    <h1>🕰️ Why does this code exist?</h1>

    <div class="summary">
        ${htmlSummary}
    </div>

    <div class="section">
        <h2>📍 Location</h2>
        <p><strong>File:</strong> <code>${context.file_path}</code></p>
        <p><strong>Lines:</strong> ${context.line_start}-${context.line_end}</p>
    </div>

    ${context.last_commit ? `
    <div class="section commit">
        <h2>📝 Last Modified</h2>
        <p><strong>Commit:</strong> <code>${context.last_commit.sha ? context.last_commit.sha.slice(0, 7) : 'unknown'}</code></p>
        <p><strong>Author:</strong> ${this.escapeHtml(context.last_commit.author || 'unknown')}</p>
        <p><strong>Date:</strong> ${context.last_commit.date || 'unknown'}</p>
        <p><strong>Message:</strong> ${this.escapeHtml(context.last_commit.message || '')}</p>
    </div>
    ` : ''}

    ${context.pr ? `
    <div class="section pr">
        <h2>🔗 Pull Request #${context.pr.number}</h2>
        <p><strong>${this.escapeHtml(context.pr.title)}</strong></p>
        ${context.pr.body ? `<p>${this.escapeHtml(context.pr.body.slice(0, 300))}${context.pr.body.length > 300 ? '...' : ''}</p>` : ''}
        ${context.pr.html_url ? `<p><a href="${context.pr.html_url}">View on GitHub →</a></p>` : ''}
        <p class="metadata">Merged: ${context.pr.merged_at ? new Date(context.pr.merged_at).toLocaleDateString() : 'Not merged'}</p>
    </div>
    ` : ''}

    ${context.issue ? `
    <div class="section issue">
        <h2>📋 Issue #${context.issue.number}</h2>
        <p><strong>${this.escapeHtml(context.issue.title)}</strong></p>
        ${context.issue.body ? `<p>${this.escapeHtml(context.issue.body.slice(0, 300))}${context.issue.body.length > 300 ? '...' : ''}</p>` : ''}
        ${context.issue.html_url ? `<p><a href="${context.issue.html_url}">View on GitHub →</a></p>` : ''}
        <p class="metadata">State: ${context.issue.state || 'unknown'}</p>
    </div>
    ` : ''}

    ${context.discussions && context.discussions.length > 0 ? `
    <div class="section">
        <h2>💬 Key Discussions</h2>
        ${context.discussions.slice(0, 3).map((d: any) => `
            <blockquote>
                <p>${this.escapeHtml(d.body ? d.body.slice(0, 200) : '')}${d.body && d.body.length > 200 ? '...' : ''}</p>
                <p class="metadata">— ${this.escapeHtml(d.author || 'unknown')}</p>
            </blockquote>
        `).join('')}
    </div>
    ` : ''}

    ${!context.pr && !context.issue ? `
    <div class="info">
        <p><strong>ℹ️ Limited Context</strong></p>
        <p>This code doesn't have linked PRs or issues. The context is based on Git history only.</p>
    </div>
    ` : ''}

    <div class="metadata" style="margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--vscode-panel-border);">
        <p>Powered by <a href="https://github.com/burak/codebase-time-machine">Codebase Time Machine</a></p>
    </div>
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
