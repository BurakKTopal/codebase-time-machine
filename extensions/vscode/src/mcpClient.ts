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
            let serverCommand = config.get<string>('serverCommand', 'uv');
            let serverArgs = config.get<string[]>('serverArgs', ['run', 'ctm-server']);
            const serverPath = config.get<string>('serverPath', '');
            let workingDirectory: string | undefined;

            // Determine working directory
            if (serverPath) {
                workingDirectory = serverPath;
            } else {
                // Auto-detect: Check if current workspace is CTM repo
                const workspaceFolders = vscode.workspace.workspaceFolders;
                if (workspaceFolders) {
                    const rootPath = workspaceFolders[0].uri.fsPath;
                    const path = require('path');
                    const fs = require('fs');
                    const pyprojectPath = path.join(rootPath, 'pyproject.toml');
                    if (fs.existsSync(pyprojectPath)) {
                        const pyproject = fs.readFileSync(pyprojectPath, 'utf-8');
                        if (pyproject.includes('ctm-server')) {
                            workingDirectory = rootPath;
                        }
                    }
                }
            }

            // If we have a working directory, create a batch file to handle it
            if (workingDirectory) {
                const path = require('path');
                const fs = require('fs');
                const os = require('os');
                const tmpDir = os.tmpdir();

                const isWindows = process.platform === 'win32';
                if (isWindows) {
                    const batchFile = path.join(tmpDir, 'ctm-start.bat');
                    const batchContent = `@echo off\ncd /d "${workingDirectory}"\n${serverCommand} ${serverArgs.join(' ')}`;
                    fs.writeFileSync(batchFile, batchContent);

                    // Windows .bat files must be executed through cmd
                    serverCommand = 'cmd';
                    serverArgs = ['/c', batchFile];
                } else {
                    const scriptFile = path.join(tmpDir, 'ctm-start.sh');
                    const scriptContent = `#!/bin/sh\ncd "${workingDirectory}"\n${serverCommand} ${serverArgs.join(' ')}`;
                    fs.writeFileSync(scriptFile, scriptContent);
                    fs.chmodSync(scriptFile, '755');
                    serverCommand = scriptFile;
                    serverArgs = [];
                }
            }

            // Log the exact command being executed
            console.log('[CTM] Starting MCP server with command:', serverCommand);
            console.log('[CTM] Arguments:', serverArgs);
            console.log('[CTM] Full command:', `${serverCommand} ${serverArgs.join(' ')}`);

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

            console.log('[CTM] Connecting to MCP server...');
            await this.client.connect(this.transport);
            this.connected = true;
            console.log('[CTM] Successfully connected to MCP server');
        } catch (error) {
            console.error('[CTM] Failed to connect to MCP server:', error);
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
