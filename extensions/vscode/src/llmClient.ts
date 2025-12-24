import Anthropic from '@anthropic-ai/sdk';
import * as vscode from 'vscode';

export class LLMClient {
    private client: Anthropic | null = null;

    constructor() {
        const apiKey = vscode.workspace.getConfiguration('ctm').get<string>('anthropicApiKey');
        if (apiKey && apiKey.trim()) {
            this.client = new Anthropic({ apiKey });
        }
    }

    async summarize(context: any): Promise<string> {
        if (!this.client) {
            return this.getFallbackSummary(context);
        }

        try {
            const prompt = this.buildPrompt(context);

            const response = await this.client.messages.create({
                model: 'claude-sonnet-4-5-20250929',
                max_tokens: 1024,
                messages: [{ role: 'user', content: prompt }]
            });

            const textContent = response.content.find(c => c.type === 'text');
            if (!textContent || textContent.type !== 'text') {
                return this.getFallbackSummary(context);
            }

            return textContent.text;
        } catch (error) {
            console.error('Error calling Anthropic API:', error);
            return this.getFallbackSummary(context);
        }
    }

    private buildPrompt(context: any): string {
        return `Explain why this code exists based on the context below. Be concise and actionable.

File: ${context.file_path}
Lines: ${context.line_start}-${context.line_end}
${context.last_commit ? `Last modified: ${context.last_commit.date}` : ''}
${context.last_commit ? `Commit: ${context.last_commit.message}` : ''}
${context.pr ? `PR: ${context.pr.title}` : ''}
${context.issue ? `Issue: ${context.issue.title}` : ''}

Full context:
${JSON.stringify(context, null, 2)}

Provide:
1. One-sentence summary of why this code exists
2. Key context from commit/PR/issue discussions
3. Technical debt or follow-up warnings if applicable

Keep it concise (3-5 paragraphs max).`;
    }

    private getFallbackSummary(context: any): string {
        let summary = `### Code Context\n\n`;

        summary += `**File:** ${context.file_path}\n`;
        summary += `**Lines:** ${context.line_start}-${context.line_end}\n\n`;

        if (context.last_commit) {
            summary += `#### Last Modified\n`;
            summary += `- **Date:** ${context.last_commit.date}\n`;
            summary += `- **Author:** ${context.last_commit.author}\n`;
            summary += `- **Message:** ${context.last_commit.message}\n\n`;
        }

        if (context.pr) {
            summary += `#### Pull Request\n`;
            summary += `- **#${context.pr.number}:** ${context.pr.title}\n`;
            if (context.pr.body) {
                summary += `- ${context.pr.body.slice(0, 200)}...\n`;
            }
            summary += `\n`;
        }

        if (context.issue) {
            summary += `#### Related Issue\n`;
            summary += `- **#${context.issue.number}:** ${context.issue.title}\n`;
            if (context.issue.body) {
                summary += `- ${context.issue.body.slice(0, 200)}...\n`;
            }
            summary += `\n`;
        }

        summary += `\n> **Note:** Configure your Anthropic API key in settings to get AI-powered summaries.\n`;
        summary += `> Currently showing raw context without LLM summarization.`;

        return summary;
    }
}
