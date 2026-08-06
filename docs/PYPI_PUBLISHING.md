<!--
SPDX-FileCopyrightText: 2026 Maurice Casey
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Publishing the Artifice Suite to PyPI

Everything that can be verified from this side has been. What remains is
account setup on pypi.org, which needs a human with the credentials.

**Verified 2026-08-06** by `scripts/check-pypi-readiness.py` and `twine check`:
all seven distributions build, carry correct PEP 639 metadata, embed their
READMEs, and — the one thing that would have broken every install — declare
their internal dependencies as **plain names**, not workspace paths.

---

## The one thing to get right: publish order

Every app declares the three shared packages by name:

```
artifice-model-harness>=0.1.0
artifice-secure-io>=0.1.0
artifice-shared-ui>=0.1.0
```

Locally, `[tool.uv.sources]` resolves those from the workspace, so nothing
complains. On PyPI there is no workspace. **If the apps are published first,
`pip install artifice-graph` on a stranger's machine fails to resolve its own
dependencies**, because they do not exist on the index yet.

> **Publish the three shared packages first. Then the four apps.**

`publish.yml` enforces this with `needs: shared-packages`, but the same order
applies when registering pending publishers and when testing on TestPyPI.

---

## Step 1 — Create the PyPI account (once)

1. Register at <https://pypi.org/account/register/>.
2. **Enable 2FA immediately** — PyPI requires it for anyone who owns a project,
   and you will not be able to create the publishers below without it.
   Account settings → *Two factor authentication* → add an authenticator app.
3. **Save the recovery codes somewhere you will still have them in two years.**
   Losing 2FA on an account that owns seven published names is a genuinely
   painful recovery.

Do the same at <https://test.pypi.org/> — it is a **separate account** with
separate credentials and separate 2FA. It is not linked to the real one.

---

## Step 2 — Add a pending publisher for each of the seven projects

None of the seven names exist on PyPI yet — confirmed 2026-08-06, all returned
404. A *pending* publisher is how you claim a name that has never been
uploaded: PyPI creates the project on first successful publish.

For **each** of the seven names below: PyPI → *Your projects* →
*Publishing* → *Add a new pending publisher* → **GitHub**.

Enter **exactly** this, for every one:

| Field | Value |
|---|---|
| PyPI Project Name | *(the name from the list below)* |
| Owner | `Muggwoffin` |
| Repository name | `artifice-suite` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

The seven names, **in publish order**:

1. `artifice-model-harness`
2. `artifice-secure-io`
3. `artifice-shared-ui`
4. `artifice-ocr`
5. `artifice-draft`
6. `artifice-graph`
7. `artifice-transcribe`

**The environment name must be `pypi`.** It matches `environment: pypi` in
`publish.yml`. If they differ, PyPI rejects the token exchange with an error
that reads like a permissions problem rather than a name mismatch — this is the
single most common way this setup fails.

Repeat all seven on TestPyPI if you want to rehearse (recommended, see Step 3).

---

## Step 3 — Rehearse on TestPyPI

Actions → **Publish to PyPI** → *Run workflow* → target: `testpypi`.

Then confirm a clean machine can actually resolve it:

```bash
uv run --with artifice-graph \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  artifice-graph --data-dir
```

The `--extra-index-url` is needed because TestPyPI does not carry the real
third-party dependencies (pydantic, fastapi, …), only what you uploaded there.

**Why rehearse:** a version number on PyPI is burned permanently. You cannot
re-upload `0.1.0` after deleting it, so a bad first upload costs you the
version, not just some time.

---

## Step 4 — Publish for real

Two ways, both already wired:

- **Tag** — `git tag v0.1.0 && git push origin v0.1.0`. This also fires the
  existing `Release Gate`, which checks that tag, package versions and
  `CITATION.cff` agree, and it triggers Zenodo DOI minting.
- **Manual** — Actions → *Publish to PyPI* → *Run workflow* → target: `pypi`.

Watch that the `shared-packages` job finishes before `apps` starts. That is the
ordering constraint doing its job.

---

## Step 5 — Verify from outside

```bash
uv tool install artifice-graph
artifice-graph --data-dir
```

Check each project page actually renders its README rather than showing a blank
description.

---

## After the first publish

- The pending publishers become ordinary publishers automatically.
- **Consider upper bounds on the internal pins.** `>=0.1.0` is loose once these
  names are public — nothing stops a future `artifice-model-harness` 2.0 being
  pulled into an old app. `~=0.1.0` would prevent that.
- `README.md` still tells users to clone the workspace. Once these are on PyPI,
  `uv tool install artifice-<app>` is the real install story and the README
  should lead with it.

---

## What is deliberately NOT automated

No API token exists anywhere in this repository, and none should be created.
Trusted Publishing needs no stored credential, which is the only arrangement
compatible with the Zero Secrets Policy. If you are ever asked to paste a PyPI
token into an Actions secret, something has gone wrong with the setup above.

---

## Re-checking readiness

```bash
uv run python scripts/check-pypi-readiness.py
```

Builds all seven and inspects the **built artifacts**, not the source tree —
this repo has shipped four packaging bugs that no test could reach, because
tests run against `src/` while the defect exists only in the wheel.
