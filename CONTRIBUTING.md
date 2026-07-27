# Contributing to Artifice Suite

We welcome contributions that adhere to our local-first, anti-ELIZA harness philosophy and design system.

## Pull Request Requirements

1. **Structured Harness Validation**: Any new feature or model connector must use `packages/model-harness` with strict schema validation. No freeform chat wrappers are permitted.
2. **Design System Compliance**: Frontend contributions must strictly follow `Design_Philosophy.md` (The New Masses Design System tokens, typography, and anti-patterns).
3. **Agent Verification**:
   - **Tester (`kimi-k3`)**: Must execute test suites and pass regression checks without errors.
   - **Architecture Auditor (`glm-5.2`)**: Must verify structural parity and clean package boundaries.
   - **Security Auditor (`claude-3-5-sonnet`)**: Must verify local-first data isolation and absence of secret leakage.
4. **Local Testing**: Run `pnpm test` and `docker-compose build` locally before submitting pull requests.
