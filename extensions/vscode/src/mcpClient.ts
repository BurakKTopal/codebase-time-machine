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
            const serverPath = config.get<string>('serverPath', '');
            const githubToken = config.get<string>('githubToken', '');

            // Auto-detect server installation or use manual config
            const detectionResult = await this.detectServerCommand(config, serverPath);

            let serverCommand = detectionResult.command;
            let serverArgs = detectionResult.args;
            let workingDirectory = detectionResult.workingDirectory;

            // Override with manual serverPath if provided
            if (serverPath) {
                workingDirectory = serverPath;
            }

            // If we have a working directory, create a wrapper script to handle it
            if (workingDirectory) {
                const path = require('path');
                const fs = require('fs');
                const os = require('os');
                const tmpDir = os.tmpdir();

                const isWindows = process.platform === 'win32';
                if (isWindows) {
                    // Create a Node.js wrapper that spawns with correct cwd
                    const wrapperFile = path.join(tmpDir, 'ctm-wrapper.js');
                    const wrapperContent = `const { spawn } = require('child_process');

console.log('Codebase Time Machine - MCP Server');
console.log('Working directory: ${workingDirectory.replace(/\\/g, '\\\\')}');
console.log('Command: ${serverCommand} ${serverArgs.join(' ')}');

const proc = spawn('${serverCommand}', ${JSON.stringify(serverArgs)}, {
    cwd: '${workingDirectory.replace(/\\/g, '\\\\')}',
    stdio: 'inherit',
    windowsHide: true
});

proc.on('exit', code => {
    process.exit(code);
});`;
                    fs.writeFileSync(wrapperFile, wrapperContent);

                    // Run the wrapper with node
                    serverCommand = 'node';
                    serverArgs = [wrapperFile];
                } else {
                    const scriptFile = path.join(tmpDir, 'ctm-start.sh');
                    const scriptContent = `#!/bin/sh\ncd "${workingDirectory}"\n${serverCommand} ${serverArgs.join(' ')}`;
                    fs.writeFileSync(scriptFile, scriptContent);
                    fs.chmodSync(scriptFile, '755');
                    serverCommand = scriptFile;
                    serverArgs = [];
                }
            }

            // Build environment with GitHub token
            const env = { ...process.env } as Record<string, string>;
            if (githubToken) {
                env['GITHUB_TOKEN'] = githubToken;
                console.log('[CTM] GitHub token configured - private repos and higher rate limits enabled');
            }

            // Log the exact command being executed
            console.log('[CTM] Starting MCP server with command:', serverCommand);
            console.log('[CTM] Arguments:', serverArgs);
            console.log('[CTM] Full command:', `${serverCommand} ${serverArgs.join(' ')}`);
            if (workingDirectory) {
                console.log('[CTM] Working directory:', workingDirectory);
            }

            this.transport = new StdioClientTransport({
                command: serverCommand,
                args: serverArgs,
                env: env
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

    async listTools(): Promise<any[]> {
        if (!this.client || !this.connected) {
            throw new Error('MCP client not connected. Call connect() first.');
        }

        try {
            const result = await this.client.listTools();
            return result.tools || [];
        } catch (error) {
            throw new Error(`Failed to list tools: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    async callTool(name: string, args: any): Promise<any> {
        if (!this.client || !this.connected) {
            throw new Error('MCP client not connected. Call connect() first.');
        }

        try {
            const result = await this.client.callTool({
                name: name,
                arguments: args as Record<string, unknown>
            });

            if (!result.content || (Array.isArray(result.content) && result.content.length === 0)) {
                throw new Error('No content returned from MCP server');
            }

            const content = Array.isArray(result.content) ? result.content : [result.content];
            const textContent = content[0] as any;

            if (textContent.type !== 'text') {
                throw new Error('Expected text content from MCP server');
            }

            // Try to parse as JSON
            try {
                return JSON.parse(textContent.text);
            } catch (parseError) {
                // If it's not JSON, it might be an error message from the MCP server
                console.error('[CTM] Tool returned non-JSON response:', textContent.text);
                throw new Error(`Tool ${name} returned invalid response: ${textContent.text}`);
            }
        } catch (error) {
            throw new Error(`Failed to call tool ${name}: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    async getLineContext(params: GetLineContextParams): Promise<any> {
        return this.callTool('get_line_context', params);
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

    private async detectServerCommand(
        config: vscode.WorkspaceConfiguration,
        serverPath: string
    ): Promise<{ command: string; args: string[]; workingDirectory?: string }> {
        const { execSync } = require('child_process');
        const fs = require('fs');
        const path = require('path');

        // Default command from package.json
        const DEFAULT_COMMAND = ['python', '-m', 'ctm_mcp_server.stdio_server'];

        // Get user's serverCommand setting
        const serverCommand = config.get<string[]>('serverCommand', DEFAULT_COMMAND);

        // Priority 1: User manually configured serverCommand (non-default)
        const isCustomCommand = JSON.stringify(serverCommand) !== JSON.stringify(DEFAULT_COMMAND);

        if (isCustomCommand && serverCommand.length > 0) {
            console.log('[CTM] Using manually configured command:', serverCommand.join(' '));
            const [command, ...args] = serverCommand;
            return {
                command,
                args,
                workingDirectory: serverPath || undefined
            };
        }

        // Priority 2: serverPath is set - Local development mode with uv
        if (serverPath) {
            const pyprojectPath = path.join(serverPath, 'pyproject.toml');
            if (fs.existsSync(pyprojectPath)) {
                const pyproject = fs.readFileSync(pyprojectPath, 'utf-8');
                if (pyproject.includes('ctm-server')) {
                    console.log('[CTM] Local development mode - using uv at:', serverPath);
                    return {
                        command: 'uv',
                        args: ['run', 'ctm-server'],
                        workingDirectory: serverPath
                    };
                }
            }
            console.warn('[CTM] serverPath set but pyproject.toml not found or invalid');
        }

        // Priority 3: Check if ctm-server is in PATH (pip/pipx install - default for users)
        try {
            execSync('ctm-server --version', { stdio: 'ignore' });
            console.log('[CTM] Using pip/pipx package installation');
            return {
                command: 'ctm-server',
                args: [],
                workingDirectory: undefined
            };
        } catch {
            // Not in PATH, continue checking other methods
        }

        // Priority 4: Try Python module directly (if package installed but no ctm-server in PATH)
        // Try python first, then python3 (for Linux systems)
        for (const pythonCmd of ['python', 'python3']) {
            try {
                execSync(`${pythonCmd} -m ctm_mcp_server.stdio_server --help`, { stdio: 'ignore', timeout: 2000 });
                console.log(`[CTM] Using Python package installation (${pythonCmd})`);
                return {
                    command: pythonCmd,
                    args: ['-m', 'ctm_mcp_server.stdio_server'],
                    workingDirectory: undefined
                };
            } catch {
                // Try next Python command
            }
        }

        // Priority 5: Try uv tool install (global)
        try {
            const uvToolList = execSync('uv tool list', { encoding: 'utf-8', stdio: 'pipe' });
            if (uvToolList.includes('codebase-time-machine')) {
                console.log('[CTM] Using uv tool installation');
                return {
                    command: 'uv',
                    args: ['tool', 'run', 'ctm-server'],
                    workingDirectory: undefined
                };
            }
        } catch {
            // uv not available or tool not installed
        }

        // No installation found
        throw new Error(
            'CTM server not found. Please install it:\n' +
            '  - Recommended: pip install codebase-time-machine\n' +
            '  - Or set ctm.serverPath to your local CTM repository'
        );
    }
}
