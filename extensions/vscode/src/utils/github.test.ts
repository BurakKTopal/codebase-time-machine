import * as assert from 'assert';
import { getRelativePath } from './github';

describe('GitHub Utilities', () => {
    describe('getRelativePath', () => {
        it('should convert absolute Windows path to relative path with forward slashes', () => {
            const absolutePath = 'c:\\Users\\Burak\\CodebaseTimeMachine\\src\\file.ts';
            const rootPath = 'c:\\Users\\Burak\\CodebaseTimeMachine';
            const result = getRelativePath(absolutePath, rootPath);

            assert.strictEqual(result, 'src/file.ts');
        });

        it('should convert absolute Unix path to relative path', () => {
            const absolutePath = '/home/user/project/src/file.ts';
            const rootPath = '/home/user/project';
            const result = getRelativePath(absolutePath, rootPath);

            assert.strictEqual(result, 'src/file.ts');
        });

        it('should handle nested directories correctly', () => {
            const absolutePath = 'c:\\Users\\Burak\\CodebaseTimeMachine\\extensions\\vscode\\src\\utils\\github.ts';
            const rootPath = 'c:\\Users\\Burak\\CodebaseTimeMachine';
            const result = getRelativePath(absolutePath, rootPath);

            assert.strictEqual(result, 'extensions/vscode/src/utils/github.ts');
        });

        it('should return empty string if paths are the same', () => {
            const path = 'c:\\Users\\Burak\\CodebaseTimeMachine';
            const result = getRelativePath(path, path);

            assert.strictEqual(result, '');
        });

        it('should handle single file in root directory', () => {
            const absolutePath = 'c:\\Users\\Burak\\CodebaseTimeMachine\\README.md';
            const rootPath = 'c:\\Users\\Burak\\CodebaseTimeMachine';
            const result = getRelativePath(absolutePath, rootPath);

            assert.strictEqual(result, 'README.md');
        });
    });
});
