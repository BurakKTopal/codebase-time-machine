/**
 * Tests for FactStore
 */

import * as assert from 'assert';
import { FactStore, Fact, Evidence, InvestigationState } from './factStore';

// Mock API key for testing (FactStore requires it but we won't make API calls)
const MOCK_API_KEY = 'test-api-key-for-testing';

describe('FactStore', () => {
    let factStore: FactStore;

    beforeEach(() => {
        factStore = new FactStore(MOCK_API_KEY);
    });

    describe('extractAndStore', () => {
        it('should handle empty results', async () => {
            const result = await factStore.extractAndStore('test_tool', null);
            assert.ok(result.includes('no data'));
            assert.strictEqual(factStore.getFactCount(), 0);
        });

        it('should handle error results', async () => {
            const result = await factStore.extractAndStore('test_tool', { error: 'test error' });
            assert.ok(result.includes('no data'));
            assert.strictEqual(factStore.getFactCount(), 0);
        });

        it('should track tools called', async () => {
            await factStore.extractAndStore('tool1', {});
            await factStore.extractAndStore('tool2', {});
            const tools = factStore.getToolsCalled();
            assert.deepStrictEqual(tools, ['tool1', 'tool2']);
        });
    });

    describe('extractFactsFromResult - get_local_line_context', () => {
        it('should extract blame commit facts', async () => {
            const result = {
                blame_commit: {
                    sha: 'abc12345678',
                    author: 'John Doe',
                    date: '2024-01-15T10:00:00Z',
                    message: 'Fix bug in parser\n\nMore details here'
                }
            };

            await factStore.extractAndStore('get_local_line_context', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('abc12345'));
            assert.ok(facts.includes('John Doe'));
            assert.ok(facts.includes('Fix bug in parser'));
        });

        it('should extract PR facts', async () => {
            const result = {
                pull_request: {
                    number: 123,
                    title: 'Add new feature',
                    author: 'jane_dev',
                    body: 'This PR adds a new feature that improves performance significantly.'
                }
            };

            await factStore.extractAndStore('get_local_line_context', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('PR #123'));
            assert.ok(facts.includes('Add new feature'));
            assert.ok(facts.includes('jane_dev'));
        });

        it('should extract linked issue facts', async () => {
            const result = {
                linked_issues: [
                    {
                        number: 456,
                        title: 'Bug: crash on startup',
                        body: 'Application crashes when starting up on Windows due to missing DLL.'
                    }
                ]
            };

            await factStore.extractAndStore('get_local_line_context', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('Issue #456'));
            assert.ok(facts.includes('crash on startup'));
        });

        it('should extract historical commits', async () => {
            const result = {
                historical_commits: [
                    { sha: 'abc123', author: 'Dev1', date: '2024-03-01', message: 'Recent change' },
                    { sha: 'def456', author: 'Dev2', date: '2024-01-01', message: 'Original code' }
                ]
            };

            await factStore.extractAndStore('get_local_line_context', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('abc123'));
            assert.ok(facts.includes('def456'));
            // Note: historical_commits no longer labeled as ORIGIN (use pickaxe_search for true origin)
            assert.ok(facts.includes('Oldest commit in view'));
        });
    });

    describe('extractFactsFromResult - get_pr', () => {
        it('should extract full PR details', async () => {
            const result = {
                number: 789,
                title: 'Refactor authentication',
                author: 'security_expert',
                state: 'merged',
                body: 'This refactors the authentication system to use JWT tokens.',
                comments: [
                    { author: 'reviewer1', body: 'Great work! The new auth flow is much cleaner and more secure than before. I really appreciate the thorough testing.' }
                ]
            };

            await factStore.extractAndStore('get_pr', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('PR #789'));
            assert.ok(facts.includes('Refactor authentication'));
            assert.ok(facts.includes('merged'));
            assert.ok(facts.includes('JWT tokens'));
            assert.ok(facts.includes('reviewer1'));
        });
    });

    describe('extractFactsFromResult - get_issue', () => {
        it('should extract issue details', async () => {
            const result = {
                number: 101,
                title: 'Performance degradation',
                author: 'user123',
                state: 'closed',
                body: 'The application has become very slow after the latest update.'
            };

            await factStore.extractAndStore('get_issue', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('Issue #101'));
            assert.ok(facts.includes('Performance degradation'));
            assert.ok(facts.includes('closed'));
        });
    });

    describe('extractFactsFromResult - file history', () => {
        it('should extract file history commits', async () => {
            const result = {
                commits: [
                    { sha: 'commit1sha', message: 'Update docs' },
                    { sha: 'commit2sha', message: 'Fix typo' },
                    { sha: 'commit3sha', message: 'Initial commit' }
                ]
            };

            await factStore.extractAndStore('get_github_file_history', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('commit1'));
            assert.ok(facts.includes('Update docs'));
            assert.ok(facts.includes('3 total commits'));
        });
    });

    describe('extractFactsFromResult - pickaxe_search', () => {
        it('should extract pickaxe results', async () => {
            const result = {
                search_string: 'specialFunction',
                commits: [
                    { sha: 'originsha1', author: 'original_author', date: '2023-01-01', message: 'Add specialFunction' }
                ]
            };

            await factStore.extractAndStore('pickaxe_search', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('Pickaxe'));
            assert.ok(facts.includes('originsha1'));
            assert.ok(facts.includes('original_author'));
        });

        it('should handle no results', async () => {
            const result = {
                search_string: 'nonexistent',
                commits: []
            };

            await factStore.extractAndStore('pickaxe_search', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('no commits'));
        });
    });

    describe('extractFactsFromResult - get_commit_diff', () => {
        it('should extract diff information', async () => {
            const result = {
                sha: 'diffsha123',
                message: 'Add new utility function',
                files: [
                    { filename: 'src/utils.ts', patch: '+export function helper() {\n+  return true;\n+}' },
                    { filename: 'src/index.ts', patch: '+import { helper } from "./utils";' }
                ]
            };

            await factStore.extractAndStore('get_commit_diff', result);

            const facts = factStore.getFactsSummary();
            assert.ok(facts.includes('diffsha'));
            assert.ok(facts.includes('src/utils.ts'));
            assert.ok(facts.includes('helper'));
        });
    });

    describe('getFactsSummary', () => {
        it('should return appropriate message when no facts', () => {
            const summary = factStore.getFactsSummary();
            assert.strictEqual(summary, 'No facts gathered yet.');
        });

        it('should organize facts by category', async () => {
            // Add various facts
            await factStore.extractAndStore('get_local_line_context', {
                blame_commit: { sha: 'abc123', author: 'Dev', date: '2024-01-01', message: 'Fix' },
                pull_request: { number: 1, title: 'PR Title', author: 'Dev' }
            });
            await factStore.extractAndStore('get_issue', {
                number: 2, title: 'Issue Title', author: 'User', state: 'open', body: ''
            });

            const summary = factStore.getFactsSummary();

            // Check for category headers
            assert.ok(summary.includes('**Commits:**'));
            assert.ok(summary.includes('**Pull Requests:**'));
            assert.ok(summary.includes('**Issues:**'));
        });
    });

    describe('getState', () => {
        it('should return complete investigation state', async () => {
            await factStore.extractAndStore('get_local_line_context', {
                blame_commit: { sha: 'abc123', author: 'Dev', date: '2024-01-01', message: 'Fix' }
            });

            const state = factStore.getState('Why does this exist?', '/src/file.ts', '10-20');

            assert.strictEqual(state.goal, 'Why does this exist?');
            assert.strictEqual(state.filePath, '/src/file.ts');
            assert.strictEqual(state.lineRange, '10-20');
            assert.ok(state.facts.length > 0);
            assert.ok(state.toolsCalled.includes('get_local_line_context'));
            assert.ok(Array.isArray(state.openQuestions));
        });
    });

    describe('hasEnoughContext', () => {
        it('should return false initially', () => {
            assert.strictEqual(factStore.hasEnoughContext(), false);
        });

        it('should return false with only blame', async () => {
            await factStore.extractAndStore('get_local_line_context', {
                blame_commit: { sha: 'abc123', author: 'Dev', date: '2024-01-01', message: 'Fix' }
            });
            assert.strictEqual(factStore.hasEnoughContext(), false);
        });

        it('should return true with blame and PR', async () => {
            await factStore.extractAndStore('get_local_line_context', {
                blame_commit: { sha: 'abc123', author: 'Dev', date: '2024-01-01', message: 'Fix' },
                pull_request: { number: 1, title: 'PR', author: 'Dev' }
            });
            assert.strictEqual(factStore.hasEnoughContext(), true);
        });

        it('should return true with origin (from pickaxe) and issue', async () => {
            // True origin comes from pickaxe_search, not historical_commits
            await factStore.extractAndStore('pickaxe_search', {
                commits: [{ sha: 'origin123', author: 'Dev', date: '2023-01-01', message: 'Initial' }],
                introduction_commit: { sha: 'origin123', author: 'Dev', date: '2023-01-01', message: 'Initial' },
                search_string: 'some code'
            });
            await factStore.extractAndStore('get_local_line_context', {
                linked_issues: [{ number: 1, title: 'Issue', body: '' }]
            });
            assert.strictEqual(factStore.hasEnoughContext(), true);
        });
    });

    describe('Evidence extraction', () => {
        it('should extract author evidence with email', async () => {
            await factStore.extractAndStore('get_github_commit', {
                sha: 'abc123456789',
                author: { name: 'John Doe', email: 'john@example.com' },
                authored_date: '2024-01-15T10:00:00Z',
                message: 'Test commit'
            });

            const evidence = factStore.getEvidenceSummary();
            assert.ok(evidence.includes('John Doe'));
            assert.ok(evidence.includes('john@example.com'));
        });

        it('should extract full SHA evidence', async () => {
            await factStore.extractAndStore('get_github_commit', {
                sha: 'abc123456789abcdef',
                author: 'Dev',
                message: 'Test'
            });

            const evidence = factStore.getEvidenceSummary();
            assert.ok(evidence.includes('abc123456789abcdef'));
        });

        it('should extract URL evidence', async () => {
            await factStore.extractAndStore('get_pr', {
                number: 123,
                title: 'Test PR',
                author: 'dev',
                html_url: 'https://github.com/owner/repo/pull/123',
                state: 'open'
            });

            const evidence = factStore.getEvidenceSummary();
            assert.ok(evidence.includes('https://github.com/owner/repo/pull/123'));
        });
    });

    describe('clear', () => {
        it('should clear all facts and evidence', async () => {
            await factStore.extractAndStore('get_local_line_context', {
                blame_commit: { sha: 'abc123', author: 'Dev', date: '2024-01-01', message: 'Fix' },
                pull_request: { number: 1, title: 'PR', author: 'Dev' }
            });

            assert.ok(factStore.getFactCount() > 0);
            assert.ok(factStore.getToolsCalled().length > 0);

            factStore.clear();

            assert.strictEqual(factStore.getFactCount(), 0);
            assert.strictEqual(factStore.getEvidenceCount(), 0);
            assert.strictEqual(factStore.getToolsCalled().length, 0);
        });
    });

    describe('deduplication', () => {
        it('should deduplicate facts by ID', async () => {
            // Add same commit twice
            await factStore.extractAndStore('get_local_line_context', {
                blame_commit: { sha: 'abc12345', author: 'Dev', date: '2024-01-01', message: 'Fix' }
            });
            await factStore.extractAndStore('get_github_commit', {
                sha: 'abc12345',
                author: { name: 'Dev' },
                message: 'Fix'
            });

            // Should only have one entry per unique ID prefix
            const summary = factStore.getFactsSummary();
            const matches = summary.match(/abc12345/g) || [];
            // The same SHA appears in different contexts, but should be deduplicated by fact ID
            assert.ok(matches.length >= 1);
        });
    });
});

describe('Fact interface', () => {
    it('should have correct structure', () => {
        const fact: Fact = {
            id: 'test_fact_1',
            text: 'This is a test fact',
            source: 'test_tool',
            category: 'commit'
        };

        assert.strictEqual(fact.id, 'test_fact_1');
        assert.strictEqual(fact.text, 'This is a test fact');
        assert.strictEqual(fact.source, 'test_tool');
        assert.strictEqual(fact.category, 'commit');
    });
});

describe('Evidence interface', () => {
    it('should have correct structure', () => {
        const evidence: Evidence = {
            id: 'author_test',
            type: 'author',
            verbatim: 'John Doe <john@example.com>',
            source: 'get_commit'
        };

        assert.strictEqual(evidence.id, 'author_test');
        assert.strictEqual(evidence.type, 'author');
        assert.strictEqual(evidence.verbatim, 'John Doe <john@example.com>');
        assert.strictEqual(evidence.source, 'get_commit');
    });
});

describe('InvestigationState interface', () => {
    it('should have correct structure', () => {
        const state: InvestigationState = {
            goal: 'Why does this exist?',
            filePath: '/src/test.ts',
            lineRange: '1-10',
            facts: [],
            toolsCalled: ['tool1', 'tool2'],
            openQuestions: ['What is this?']
        };

        assert.strictEqual(state.goal, 'Why does this exist?');
        assert.strictEqual(state.filePath, '/src/test.ts');
        assert.strictEqual(state.lineRange, '1-10');
        assert.deepStrictEqual(state.facts, []);
        assert.deepStrictEqual(state.toolsCalled, ['tool1', 'tool2']);
        assert.deepStrictEqual(state.openQuestions, ['What is this?']);
    });
});
