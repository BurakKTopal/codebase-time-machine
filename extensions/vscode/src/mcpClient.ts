import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import * as vscode from 'vscode';

export interface GetLineContextParams extends Record<string, unknown> {
    owner: string;
    repo: string;
    file_path: string;
    line_start: number;
    line_end: number;
}

export class MCPClient {
    private client: Client | null = null;
    private transport: StdioClientTransport | null = null;
    private connected: boolean = false;

    async connect(): Promise<void> {
        if (this.connected) {
            return;
        }

        try {
            const config = vscode.workspace.getConfiguration('ctm');
            const serverCommand = config.get<string>('serverCommand', 'uv');
            const serverArgs = config.get<string[]>('serverArgs', ['run', 'ctm-server']);

            this.transport = new StdioClientTransport({
                command: serverCommand,
                args: serverArgs,
                env: process.env as Record<string, string>
            });

            this.client = new Client({
                name: 'ctm-vscode',
                version: '0.1.0'
            }, {
                capabilities: {}
            });

            await this.client.connect(this.transport);
            this.connected = true;
        } catch (error) {
            throw new Error(`Failed to connect to CTM server: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    async getLineContext(params: GetLineContextParams): Promise<any> {
        if (!this.client || !this.connected) {
            throw new Error('MCP client not connected. Call connect() first.');
        }

        try {
            const result = await this.client.callTool({
                name: 'get_line_context',
                arguments: params as Record<string, unknown>
            });

            if (!result.content || (Array.isArray(result.content) && result.content.length === 0)) {
                throw new Error('No content returned from MCP server');
            }

            const content = Array.isArray(result.content) ? result.content : [result.content];
            const textContent = content[0] as any;

            if (textContent.type !== 'text') {
                throw new Error('Expected text content from MCP server');
            }

            return JSON.parse(textContent.text);
        } catch (error) {
            throw new Error(`Failed to get line context: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    async disconnect(): Promise<void> {
        if (this.client) {
            try {
                await this.client.close();
            } catch (error) {
                console.error('Error closing MCP client:', error);
            }
            this.client = null;
            this.transport = null;
            this.connected = false;
        }
    }

    isConnected(): boolean {
        return this.connected;
    }
}
