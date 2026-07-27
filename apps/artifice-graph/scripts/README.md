# Model Discovery and Connection Scripts

This folder contains scripts for discovering available models and testing connections across different LLM platforms (Ollama, LM Studio, vLLM, OpenAI, etc.).

## Available Scripts

### 1. model_checker.py - Unified Model Discovery

A comprehensive tool for checking model availability and capabilities across different platforms:

- **Features**:
  - Check Ollama servers (local)
  - Check OpenAI-compatible endpoints
  - Validate vision/multimodal model capabilities
  - Cross-platform compatibility testing

```bash
python model_checker.py --help
```

### 2. model_fixer.py - Environment Setup Helper

A tool to help set up and troubleshoot model runner environments:

- **Features**:
  - Generate configuration snippets
  - Set up environment variables
  - Generate curl commands for testing
  - Create OLLAMA_ORIGINS=* recommendations

```bash
python model_fixer.py --help
```

### 3. local_setup.py - Quickstart Setup

A script to quickly set up local model runners:

- **Features**:
  - Download and run Ollama
  - Install and start LM Studio
  - Set up vLLM or LocalAI
  - Generate shell scripts for automation

```bash
python local_setup.py --help
```

## Usage Examples

### Check Ollama Models

```bash
python model_checker.py --ollama http://localhost:11434
```

### Check LM Studio

```bash
python model_checker.py --lmstudio http://localhost:1234
```

### Check vLLM

```bash
python model_checker.py --vllm http://localhost:8080
```

### Check OpenAI-Compatible

```bash
python model_checker.py --openai https://api.openai.com/v1
```

### Setup Environment for Local Testing

```bash
python model_fixer.py --setup-local
```

## Installation

```bash
pip install -r requirements.txt
```

## Requirements

```txt
httpx>=0.27.0
shlex>=0.1.2
```

## Configuration

Create a `settings.json` file for default configuration:

```json
{
  "ollama": "http://localhost:11434",
  "lmstudio": "http://localhost:1234",
  "vllm": "http://localhost:8080",
  "openai": "https://api.openai.com/v1"
}
```

## Testing

```bash
python -m pytest tests/
```

## Reports

- [x] Backward compatibility maintained
- [x] BYOM Configuration UI implemented
- [x] Model discovery implemented
- [x] Connection status indicators added
- [x] Vision capability detection added
- [x] Streaming support added
- [x] User preferences persistence implemented
- [x] CLI configuration updated

## Issues

- [ ] Web interface styling improvements
- [ ] Additional model runner support (Jan.ai, etc.)
- [ ] Enhanced logging and monitoring
