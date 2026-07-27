export interface ModelConnectorConfig {
  provider: 'ollama' | 'lm-studio' | 'generic-api' | 'whisper' | 'parakeet';
  endpoint: string;
  apiKey?: string;
  model: string;
}

// Universal BYOM connector & schema validator
