import * as assert from 'assert';
import { getRelativePath } from './github';

describe('GitHub Utilities', () => {
    describe('getRelativePath', () => {
        // Use Unix-style paths for cross-platform compatibility in tests
        // (Windows can handle forward slashes, Linux cannot handle backslashes)

        it('should convert absolute path to relative path', () => {
            const absolutePath = '/home/user/CodebaseTimeMachine/src/file.ts';
            const rootPath = '/home/user/CodebaseTimeMachine';
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
            const absolutePath = '/home/user/CodebaseTimeMachine/extensions/vscode/src/utils/github.ts';
            const rootPath = '/home/user/CodebaseTimeMachine';
            const result = getRelativePath(absolutePath, rootPath);

            assert.strictEqual(result, 'extensions/vscode/src/utils/github.ts');
        });

        it('should return empty string if paths are the same', () => {
            const testPath = '/home/user/CodebaseTimeMachine';
            const result = getRelativePath(testPath, testPath);

            assert.strictEqual(result, '');
        });

        it('should handle single file in root directory', () => {
            const absolutePath = '/home/user/CodebaseTimeMachine/README.md';
            const rootPath = '/home/user/CodebaseTimeMachine';
            const result = getRelativePath(absolutePath, rootPath);

            assert.strictEqual(result, 'README.md');
        });
    });
});
