/**
 * Tests for LLM Providers
 */

import * as assert from 'assert';
import {
    createProvider,
    getAvailableProviders,
    getModelsForProvider,
    getAllModels,
    hasProvider,
    getProviderDisplayName,
    CLAUDE_MODELS,
    OPENAI_MODELS,
    GEMINI_MODELS
} from './index';

describe('Provider Registry', () => {
    describe('createProvider', () => {
        it('should create an Anthropic provider', () => {
            const provider = createProvider('anthropic', { apiKey: 'test-key' });
            assert.strictEqual(provider.name, 'anthropic');
            assert.strictEqual(provider.displayName, 'Anthropic Claude');
        });

        it('should create an OpenAI provider', () => {
            const provider = createProvider('openai', { apiKey: 'test-key' });
            assert.strictEqual(provider.name, 'openai');
            assert.strictEqual(provider.displayName, 'OpenAI');
        });

        it('should create a Gemini provider', () => {
            const provider = createProvider('gemini', { apiKey: 'test-key' });
            assert.strictEqual(provider.name, 'gemini');
            assert.strictEqual(provider.displayName, 'Google Gemini');
        });

        it('should throw error for unknown provider', () => {
            assert.throws(() => {
                createProvider('unknown', { apiKey: 'test-key' });
            }, /Unknown provider: unknown/);
        });
    });

    describe('getAvailableProviders', () => {
        it('should return all registered providers', () => {
            const providers = getAvailableProviders();
            assert.strictEqual(providers.length, 3);

            const ids = providers.map(p => p.id);
            assert.ok(ids.includes('anthropic'));
            assert.ok(ids.includes('openai'));
            assert.ok(ids.includes('gemini'));
        });

        it('should include display names', () => {
            const providers = getAvailableProviders();
            const anthropic = providers.find(p => p.id === 'anthropic');
            assert.strictEqual(anthropic?.displayName, 'Anthropic Claude');
        });
    });

    describe('getModelsForProvider', () => {
        it('should return Anthropic models', () => {
            const models = getModelsForProvider('anthropic');
            assert.ok(models.length > 0);
            assert.deepStrictEqual(models, CLAUDE_MODELS);
        });

        it('should return OpenAI models', () => {
            const models = getModelsForProvider('openai');
            assert.ok(models.length > 0);
            assert.deepStrictEqual(models, OPENAI_MODELS);
        });

        it('should return Gemini models', () => {
            const models = getModelsForProvider('gemini');
            assert.ok(models.length > 0);
            assert.deepStrictEqual(models, GEMINI_MODELS);
        });

        it('should return empty array for unknown provider', () => {
            const models = getModelsForProvider('unknown');
            assert.deepStrictEqual(models, []);
        });
    });

    describe('getAllModels', () => {
        it('should return models from all providers', () => {
            const allModels = getAllModels();
            assert.strictEqual(allModels.length, 3);

            const providerIds = allModels.map(m => m.providerId);
            assert.ok(providerIds.includes('anthropic'));
            assert.ok(providerIds.includes('openai'));
            assert.ok(providerIds.includes('gemini'));
        });
    });

    describe('hasProvider', () => {
        it('should return true for existing providers', () => {
            assert.strictEqual(hasProvider('anthropic'), true);
            assert.strictEqual(hasProvider('openai'), true);
            assert.strictEqual(hasProvider('gemini'), true);
        });

        it('should return false for unknown providers', () => {
            assert.strictEqual(hasProvider('unknown'), false);
            assert.strictEqual(hasProvider(''), false);
        });
    });

    describe('getProviderDisplayName', () => {
        it('should return display names for known providers', () => {
            assert.strictEqual(getProviderDisplayName('anthropic'), 'Anthropic Claude');
            assert.strictEqual(getProviderDisplayName('openai'), 'OpenAI');
            assert.strictEqual(getProviderDisplayName('gemini'), 'Google Gemini');
        });

        it('should return the input for unknown providers', () => {
            assert.strictEqual(getProviderDisplayName('unknown'), 'unknown');
        });
    });
});

describe('Provider Models', () => {
    describe('CLAUDE_MODELS', () => {
        it('should have required fields for each model', () => {
            for (const model of CLAUDE_MODELS) {
                assert.ok(model.id, 'Model should have an id');
                assert.ok(model.label, 'Model should have a label');
                assert.ok(model.description, 'Model should have a description');
            }
        });

        it('should include haiku and sonnet models', () => {
            const ids = CLAUDE_MODELS.map(m => m.id);
            assert.ok(ids.some(id => id.includes('haiku')));
            assert.ok(ids.some(id => id.includes('sonnet')));
            // Note: Opus disabled to prevent high costs
        });
    });

    describe('OPENAI_MODELS', () => {
        it('should have required fields for each model', () => {
            for (const model of OPENAI_MODELS) {
                assert.ok(model.id, 'Model should have an id');
                assert.ok(model.label, 'Model should have a label');
                assert.ok(model.description, 'Model should have a description');
                assert.ok(model.contextWindow, 'Model should have a context window');
            }
        });

        it('should include gpt-4 models', () => {
            const ids = OPENAI_MODELS.map(m => m.id);
            assert.ok(ids.some(id => id.includes('gpt-4')));
            // Note: o1 disabled to prevent high costs
        });
    });

    describe('GEMINI_MODELS', () => {
        it('should have required fields for each model', () => {
            for (const model of GEMINI_MODELS) {
                assert.ok(model.id, 'Model should have an id');
                assert.ok(model.label, 'Model should have a label');
                assert.ok(model.description, 'Model should have a description');
                assert.ok(model.contextWindow, 'Model should have a context window');
            }
        });

        it('should include flash models', () => {
            const ids = GEMINI_MODELS.map(m => m.id);
            assert.ok(ids.some(id => id.includes('flash')));
            // Note: Pro disabled to prevent high costs
        });
    });
});

describe('Provider Instances', () => {
    describe('AnthropicProvider', () => {
        it('should return available models', () => {
            const provider = createProvider('anthropic', { apiKey: 'test-key' });
            const models = provider.getAvailableModels();
            assert.deepStrictEqual(models, CLAUDE_MODELS);
        });
    });

    describe('OpenAIProvider', () => {
        it('should return available models', () => {
            const provider = createProvider('openai', { apiKey: 'test-key' });
            const models = provider.getAvailableModels();
            assert.deepStrictEqual(models, OPENAI_MODELS);
        });
    });

    describe('GeminiProvider', () => {
        it('should return available models', () => {
            const provider = createProvider('gemini', { apiKey: 'test-key' });
            const models = provider.getAvailableModels();
            assert.deepStrictEqual(models, GEMINI_MODELS);
        });
    });
});
