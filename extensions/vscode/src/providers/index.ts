/**
 * Provider Registry
 *
 * Central registry for all AI providers. To add a new provider:
 * 1. Create the provider class implementing ILLMProvider
 * 2. Add it to the PROVIDERS record below
 * 3. Update package.json enum for settings
 */

import { ILLMProvider, ProviderConfig, LLMModel } from './types';
import { AnthropicProvider, CLAUDE_MODELS } from './anthropic';
import { OpenAIProvider, OPENAI_MODELS } from './openai';
import { GeminiProvider, GEMINI_MODELS } from './gemini';

// Re-export types and providers for convenience
export * from './types';
export { AnthropicProvider, CLAUDE_MODELS } from './anthropic';
export { OpenAIProvider, OPENAI_MODELS } from './openai';
export { GeminiProvider, GEMINI_MODELS } from './gemini';

/**
 * Provider definition with factory and models
 */
interface ProviderDefinition {
    displayName: string;
    factory: (config: ProviderConfig) => ILLMProvider;
    models: LLMModel[];
}

/**
 * Registry of available providers
 *
 * To add a new provider (e.g., OpenAI):
 * 1. Create providers/openai.ts implementing ILLMProvider
 * 2. Add: openai: { displayName: 'OpenAI', factory: (c) => new OpenAIProvider(c), models: OPENAI_MODELS }
 */
const PROVIDERS: Record<string, ProviderDefinition> = {
    anthropic: {
        displayName: 'Anthropic Claude',
        factory: (config) => new AnthropicProvider(config),
        models: CLAUDE_MODELS,
    },
    openai: {
        displayName: 'OpenAI',
        factory: (config) => new OpenAIProvider(config),
        models: OPENAI_MODELS,
    },
    gemini: {
        displayName: 'Google Gemini',
        factory: (config) => new GeminiProvider(config),
        models: GEMINI_MODELS,
    },
};

/**
 * Create a provider instance
 * @throws Error if provider is not found
 */
export function createProvider(name: string, config: ProviderConfig): ILLMProvider {
    const provider = PROVIDERS[name];
    if (!provider) {
        const available = Object.keys(PROVIDERS).join(', ');
        throw new Error(`Unknown provider: ${name}. Available providers: ${available}`);
    }
    return provider.factory(config);
}

/**
 * Get list of available providers
 */
export function getAvailableProviders(): { id: string; displayName: string }[] {
    return Object.entries(PROVIDERS).map(([id, provider]) => ({
        id,
        displayName: provider.displayName,
    }));
}

/**
 * Get models for a specific provider
 */
export function getModelsForProvider(name: string): LLMModel[] {
    return PROVIDERS[name]?.models || [];
}

/**
 * Get all available models from all providers
 */
export function getAllModels(): { providerId: string; models: LLMModel[] }[] {
    return Object.entries(PROVIDERS).map(([id, provider]) => ({
        providerId: id,
        models: provider.models,
    }));
}

/**
 * Check if a provider exists
 */
export function hasProvider(name: string): boolean {
    return name in PROVIDERS;
}

/**
 * Get provider display name
 */
export function getProviderDisplayName(name: string): string {
    return PROVIDERS[name]?.displayName || name;
}
