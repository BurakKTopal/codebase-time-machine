// Test setup - mock vscode module
import Module from 'module';
import * as vscodeMock from './vscode-mock';

// Override require to return our mock for 'vscode'
const originalRequire = Module.prototype.require;

(Module.prototype.require as any) = function(this: any, id: string) {
    if (id === 'vscode') {
        return vscodeMock;
    }
    return originalRequire.apply(this, arguments as any);
};
