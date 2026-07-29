# Security Policy

## Supported Versions

Only the most recent release of each application receives security updates.
The current versions are listed in the respective `pyproject.toml` files under
`apps/` and `packages/`.

| Component              | Status      |
| ---------------------- | ----------- |
| artifice-ocr           | supported   |
| artifice-draft          | supported   |
| artifice-graph          | supported   |
| artifice-transcribe     | supported   |
| core-types, model-harness, shared-ui | supported   |

## Reporting a Vulnerability

**Do not open a public issue.** Report security vulnerabilities through GitHub's
private vulnerability reporting, which keeps the report visible only to you and
the maintainer until a fix is published:

> [**Report a vulnerability**](https://github.com/Muggwoffin/artifice-suite/security/advisories/new)
> — or from the repository, go to **Security → Advisories → Report a vulnerability**.

Please include enough detail to reproduce the issue: which component is
affected, the version, and a description of the behaviour you observed.

### What to expect

- **Acknowledgment:** within 5 business days.
- **Assessment:** we will confirm the issue, assess its severity, and determine
  whether a fix is warranted within 14 business days of acknowledgment.
- **Fix:** once confirmed, we aim to publish a fix within 45 days. If the fix is
  straightforward and carries low risk we may release it sooner.
- **Disclosure:** we will coordinate public disclosure with the reporter. We do
  not disclose vulnerabilities until a fix is available.

We ask that you give us reasonable time to investigate and address any issue
before disclosing it publicly.
