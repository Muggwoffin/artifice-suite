## Pull Request Template

### Description

Please include a summary of the changes and the related issue. If this PR fixes an issue, please link to it.

### Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

### Checklist

- [ ] PR is focused on one app/concern
- [ ] Tests pass for every app touched (`uv run pytest -q` from the app dir)
- [ ] `gitleaks detect` passes
- [ ] No new frontend build step or framework added
- [ ] UI changes follow Design_Philosophy.md (paper-and-ink, no chat UI)
- [ ] Any new network request falls in the allowed three tiers (never silent / disclosed on explicit action / user's own endpoint+credentials)
- [ ] New files carry SPDX headers or are covered by REUSE.toml annotations

### Additional Information

Please provide any additional information or context about the PR here.

Reference `CONTRIBUTING.md` for details.
