# Artifice Suite — Development Roadmap

**This is not a task list.** `IMPLEMENTATION_PLAN.md` is the task list — it says "do this,
then this". This document describes what kind of project the suite intends to become and how it
will get there, over a period measured in months, driven by people who do not exist yet.

Everything here is contingent on that community arriving. Mark every open question as open;
confident prose about the behaviour of contributors who have not contributed would be fiction.

---

## The community period and what it is for

The months between the first public packaging and an academic submission are not a gap to fill
with features. They are the period in which the harness idea either survives contact with
researchers who did not build it or does not.

**What counts as evidence the idea is working:**

- Issues opened by people who are not the maintainer, describing use cases the suite was not
  designed for — the harness survived an unfamiliar hand.
- Feature requests that the suite can say no to without apology, because they require a cloud
  service or a general chat interface. The ability to refuse is the ability to stay coherent.
- Pull requests that improve the implementation without changing the interface — the harness
  architecture is legible to people who did not write it.
- The bug reports that matter most are the ones about the interface lying, not about
  engineering failures: a user who could not get a result because the prompt was wrong is a
  different problem from a user who could not install the software.

**What counts as evidence the idea is not working:**

- Issues describing workflows that the harness architecture cannot support without becoming
  something else — a chat UI, a cloud service, a general-purpose assistant.
- Feature requests that treat the local-first guarantee as negotiable ("just add an option to
  use the cloud").
- A contributor who reads `packages/model-harness/contract.py` and cannot understand what it
  is for. The contract is load-bearing; it must be readable.

**This document does not invent a number of months or a threshold of issues/PRs.** Those are
maintainer decisions. The roadmap describes the *kind* of evidence, not a quantity.

---

## How contributions arrive and are handled

### Existing documents

`CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` exist and are adequate starting points, with one
gap noted below.

`CODE_OF_CONDUCT.md` is Contributor Covenant 2.1. Enforcement is by email to a single
individual (`m.casey@qub.ac.uk`). The document describes a solo maintainer, not a team.
This is accurate — there is no team — but it means that a report of unacceptable behaviour
goes to one person who must also be the decision-maker and the public face of the response.
That is a concentration of role that a larger project would distribute.

`CONTRIBUTING.md` is written for outside contributors: clone, `uv sync`, test, PR. It covers
developer tooling (ripgrep, gitleaks, shellcheck, ffmpeg), the three-tier network rule, and
the no-build-step JavaScript convention. The frontend conventions section correctly notes that
`design-system/components/` ships as `.jsx` and cannot be imported — it is specification, not
implementation. The document is thin in one place: it does not describe the review process
or who reviews PRs.

`SECURITY.md` points at GitHub private vulnerability reporting. That is the right mechanism
for a public repository.

### What the gap is

The gap is not in the existing documents; it is in what they do not describe. There is no
written policy for:

- How a PR is reviewed and by whom.
- What "architectural review" means in this project — specifically, which changes require the
  harness architecture to be applied and which do not.
- How the four apps relate to each other in terms of release cadence. They ship as one suite
  but install separately. Does a contributor fix a bug in `artifice-ocr` and release it
  independently, or does that fix ship with the next suite-wide release?

These are not rhetorical questions. They affect how issues are triaged and how contributors
understand the scope of their work. They should be written down before the first large
contribution arrives, not after.

---

## What kind of contribution is wanted

**In scope:**

- Bug fixes in any app.
- New structured-output capabilities that go through the model harness (new provider adapters,
  new schema definitions, new degradation-ladder strategies).
- UI improvements that comply with `Design_Philosophy.md`.
- Platform support: new paths through existing functionality on Windows, macOS, or Linux.
- Documentation improvements that describe what the software does without changing what the
  software is.
- Performance work that does not change behaviour.

**Out of scope — not negotiable:**

- Any feature that makes the software require a cloud service to function.
- Any feature that sends user data to a third party without the user's explicit, informed
  consent on each request.
- Any chat interface or conversational UI, regardless of how it is implemented. The harness
  architecture exists *because* Joseph Weizenbaum's 1964-67 study showed the harmful
  implications of computer-human chat interaction. This project does not revisit that
  conclusion.
- Any addition that requires a build step in the frontend JavaScript. The no-build-step rule
  is not a stylistic preference; it is the install promise. A researcher must be able to
  clone, run `uv sync`, and have working software without a Node toolchain.

**The line is the harness itself.** If a proposed feature cannot be expressed as structured
data in and structured data out — a prompt with a required response schema, a deterministic
result, and a degradation ladder — it is not a feature this project will add.

---

## Release cadence and versioning

### Current state

All four apps declare `version = "0.1.0"` in their individual `pyproject.toml` files. The
root `pyproject.toml` and `CITATION.cff` both declare `version: 1.0.0`. **This inconsistency
will confuse the first person who tries to cite a specific version.** The suite presents
itself as `1.0.0`; each app presents itself as `0.1.0`. A JOSS submission citing `artifice-suite 1.0.0` while the individual packages are `0.1.0` is a documentation inconsistency that reviewers will notice.

**This should be corrected before the first public release.** The choices are: all `1.0.0`
(ready for public use), or all `0.1.0` (not ready). A suite at `1.0.0` with individual
packages at `0.1.0` is not a choice; it is an accident.

### Cadence

No cadence is set. The maintainer's position is that the software ships when it is ready for
ordinary users, not on a schedule. This is the right instinct for software at this stage.

When a cadence becomes appropriate — when contributions arrive regularly enough that a
predictable release rhythm serves the community — the starting point is: **stable main,
release on tag, every app at the same version.** The four apps are released as a suite even
though they install separately, because they share `model-harness` and `shared-ui` at
matched versions. A change to either shared package requires a suite-wide release.

---

## The relationship between the four apps

The suite ships as one artefact (a workspace) but installs as four separate packages. A user
adopts one or some, not necessarily all. This shapes three things:

**Packaging and distribution.** A user who wants `artifice-ocr` should not need to install
`artifice-draft`. The workspace structure already supports independent installs (`uv sync
--extra ocr` vs `uv sync --extra all`). The packaging work in Phase 6 must preserve this.

**Documentation.** Each app needs its own documentation, its own quickstart, and its own
troubleshooting guide. A user of `artifice-transcribe` does not need to know that
`artifice-graph` exists. The shared `model-harness` documentation belongs in the package
itself (`packages/model-harness/README.md`), not in any app's docs.

**Issue triage.** When an issue is filed without an app label, it should be routed within one
business day. The maintainer's rule for routing: if the issue is about the harness
architecture, assign to the shared package; if it is about a specific app's behaviour,
assign to that app. A contribution that touches both goes to the shared package first —
the harness is the foundation; the apps are consumers.

---

## What must be true before academic submission

The maintainer's condition: **real community uptake and contributions.** This is not a
metric; it is a description of the project's relationship with its users. Academic submission
follows the community period, not Phase 5.

**Observable evidence of community uptake, without inventing a number:**

- The issues list contains reports from people other than the maintainer.
- At least some of those reports have been resolved by contributors other than the
  maintainer.
- The `paper.md` / `paper.bib` for JOSS has been reviewed by at least one person who was
  not part of the original development team — a reader's reaction to the description of the
  harness architecture is the most useful signal available at this stage.

**What is not evidence:** GitHub stars, fork count, or download statistics alone. These are
not meaningless, but they are not the condition. A project with many stars and no issues
has attention, not community.

**The threshold is a maintainer decision.** This document names what the evidence looks like
so that it can be recognised when it arrives, not so that it can be manufactured.

---

*Maintained by: the Artifice Suite maintainer*
*Linked from: `IMPLEMENTATION_PLAN.md` (Phase 6)*
