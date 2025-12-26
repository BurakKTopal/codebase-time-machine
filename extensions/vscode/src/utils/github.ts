import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

export interface GitHubRepoInfo {
    owner: string;
    repo: string;
    rootPath: string;
}

export function getRelativePath(absolutePath: string, rootPath: string): string {
    const relative = path.relative(rootPath, absolutePath);
    // Convert Windows backslashes to forward slashes for GitHub
    return relative.replace(/\\/g, '/');
}

export async function detectGitHubRepo(): Promise<GitHubRepoInfo> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        throw new Error('No workspace folder open');
    }

    const rootPath = workspaceFolders[0].uri.fsPath;
    const gitConfigPath = path.join(rootPath, '.git', 'config');

    if (!fs.existsSync(gitConfigPath)) {
        throw new Error('This workspace is not a Git repository');
    }

    try {
        const gitConfig = fs.readFileSync(gitConfigPath, 'utf-8');
        const remoteMatch = gitConfig.match(/\[remote "origin"\]([\s\S]*?)(?=\[|$)/);

        if (!remoteMatch) {
            throw new Error('No Git remote "origin" found');
        }

        const remoteSection = remoteMatch[1];
        const urlMatch = remoteSection.match(/url\s*=\s*(.+)/);

        if (!urlMatch) {
            throw new Error('No remote URL found in Git config');
        }

        const remoteUrl = urlMatch[1].trim();

        // Parse GitHub URL
        // Supports: https://github.com/owner/repo.git and git@github.com:owner/repo.git
        const githubMatch = remoteUrl.match(/github\.com[/:]([^/]+)\/([^/.]+?)(?:\.git)?$/);

        if (!githubMatch) {
            throw new Error('Remote URL is not a GitHub repository');
        }

        return {
            owner: githubMatch[1],
            repo: githubMatch[2],
            rootPath: rootPath
        };
    } catch (error) {
        if (error instanceof Error) {
            throw error;
        }
        throw new Error(`Failed to detect GitHub repo: ${String(error)}`);
    }
}
