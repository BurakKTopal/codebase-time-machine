import * as assert from 'assert';
import * as sinon from 'sinon';
import { CTMAgent, AgentConfig } from './agent';
import { MCPClient } from './mcpClient';

describe('CTMAgent', () => {
    let sandbox: sinon.SinonSandbox;
    let mockMCPClient: sinon.SinonStubbedInstance<MCPClient>;
    let config: AgentConfig;

    beforeEach(() => {
        sandbox = sinon.createSandbox();
        mockMCPClient = sandbox.createStubInstance(MCPClient);

        config = {
            apiKey: 'test-api-key',
            owner: 'test-owner',
            repo: 'test-repo',
            repoPath: '/path/to/repo',
            filePath: 'src/test.ts',
            lineStart: 10,
            lineEnd: 20
        };
    });

    afterEach(() => {
        sandbox.restore();
    });

    describe('buildInitialPrompt', () => {
        it('should create prompt with correct investigation target', () => {
            const agent = new CTMAgent(mockMCPClient as any, config);
            // Access private method via any cast for testing
            const prompt = (agent as any).buildInitialPrompt();

            assert.ok(prompt.includes('test-owner/test-repo'));
            assert.ok(prompt.includes('src/test.ts'));
            assert.ok(prompt.includes('10-20'));
        });

        it('should include get_local_line_context as primary tool', () => {
            const agent = new CTMAgent(mockMCPClient as any, config);
            const prompt = (agent as any).buildInitialPrompt();

            assert.ok(prompt.includes('get_local_line_context'));
            assert.ok(prompt.includes('PRIMARY'));
        });

        it('should include speed hierarchy guidance', () => {
            const agent = new CTMAgent(mockMCPClient as any, config);
            const prompt = (agent as any).buildInitialPrompt();

            assert.ok(prompt.includes('INSTANT'));
            assert.ok(prompt.includes('FAST'));
            assert.ok(prompt.includes('SLOW'));
        });

        it('should specify history_depth recommendation', () => {
            const agent = new CTMAgent(mockMCPClient as any, config);
            const prompt = (agent as any).buildInitialPrompt();

            assert.ok(prompt.includes('history_depth=5-10'));
        });
    });

    describe('getAvailableTools', () => {
        it('should convert MCP tools to Anthropic format', async () => {
            const mockTools = [
                {
                    name: 'get_line_context',
                    description: 'Get context for code lines',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            owner: { type: 'string' },
                            repo: { type: 'string' }
                        },
                        required: ['owner', 'repo']
                    }
                }
            ];

            mockMCPClient.listTools.resolves(mockTools);

            const agent = new CTMAgent(mockMCPClient as any, config);
            const tools = await (agent as any).getAvailableTools();

            assert.strictEqual(tools.length, 1);
            assert.strictEqual(tools[0].name, 'get_line_context');
            assert.strictEqual(tools[0].description, 'Get context for code lines');
            assert.ok(tools[0].input_schema);
        });

        it('should handle tools without description', async () => {
            const mockTools = [
                {
                    name: 'test_tool',
                    inputSchema: { type: 'object', properties: {} }
                }
            ];

            mockMCPClient.listTools.resolves(mockTools);

            const agent = new CTMAgent(mockMCPClient as any, config);
            const tools = await (agent as any).getAvailableTools();

            assert.strictEqual(tools.length, 1);
            assert.ok(tools[0].description.includes('test_tool'));
        });
    });

    describe('executeTool', () => {
        it('should call MCP client with correct parameters', async () => {
            const mockResult = { status: 'success', data: 'test data' };
            mockMCPClient.callTool.resolves(mockResult);

            const agent = new CTMAgent(mockMCPClient as any, config);
            const result = await (agent as any).executeTool('test_tool', { param: 'value' });

            assert.deepStrictEqual(result, mockResult);
            assert.ok(mockMCPClient.callTool.calledOnce);
            assert.ok(mockMCPClient.callTool.calledWith('test_tool', { param: 'value' }));
        });

        it('should handle tool execution errors', async () => {
            mockMCPClient.callTool.rejects(new Error('Tool execution failed'));

            const agent = new CTMAgent(mockMCPClient as any, config);

            try {
                await (agent as any).executeTool('test_tool', {});
                assert.fail('Should have thrown error');
            } catch (error) {
                assert.ok(error instanceof Error);
                assert.ok((error as Error).message.includes('Tool execution failed'));
            }
        });
    });
});
