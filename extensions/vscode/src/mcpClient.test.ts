import * as assert from 'assert';
import * as sinon from 'sinon';
import { MCPClient } from './mcpClient';

describe('MCPClient', () => {
    let mcpClient: MCPClient;
    let sandbox: sinon.SinonSandbox;

    beforeEach(() => {
        mcpClient = new MCPClient();
        sandbox = sinon.createSandbox();
    });

    afterEach(() => {
        sandbox.restore();
    });

    describe('isConnected', () => {
        it('should return false when not connected', () => {
            assert.strictEqual(mcpClient.isConnected(), false);
        });
    });

    describe('listTools', () => {
        it('should throw error when not connected', async () => {
            try {
                await mcpClient.listTools();
                assert.fail('Should have thrown error');
            } catch (error) {
                assert.ok(error instanceof Error);
                assert.ok((error as Error).message.includes('not connected'));
            }
        });
    });

    describe('callTool', () => {
        it('should throw error when not connected', async () => {
            try {
                await mcpClient.callTool('test_tool', {});
                assert.fail('Should have thrown error');
            } catch (error) {
                assert.ok(error instanceof Error);
                assert.ok((error as Error).message.includes('not connected'));
            }
        });
    });

    describe('getLineContext', () => {
        it('should throw error when not connected', async () => {
            try {
                await mcpClient.getLineContext({
                    owner: 'test',
                    repo: 'test',
                    file_path: 'test.ts',
                    line_start: 1,
                    line_end: 1
                });
                assert.fail('Should have thrown error');
            } catch (error) {
                assert.ok(error instanceof Error);
                assert.ok((error as Error).message.includes('not connected'));
            }
        });
    });

    describe('disconnect', () => {
        it('should handle disconnect gracefully when not connected', async () => {
            // Should not throw
            await mcpClient.disconnect();
            assert.strictEqual(mcpClient.isConnected(), false);
        });
    });
});
