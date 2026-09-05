# Desktop interoperability testing

Artifice uses real Tropy processes as an opt-in compatibility layer above the
fast mocked and SQLite-fixture tests. The live layer verifies the contract that
fixtures cannot: Tropy startup, project discovery, JSON-LD import, versioned API
routes, photo lookup, note creation, note retrieval, and duplicate detection.

The live test always creates a temporary Tropy profile and temporary project.
It never opens or writes a user's profile or research project. Third-party
source, native modules, profiles, and logs stay under ignored `.interop/` or the
test temporary directory.

## Linux and WSL2

Two versions are pinned in `scripts/interop/versions.env`:

- `stable` is the required compatibility baseline, currently Tropy 1.17.3.
- `canary` is an exact upstream-main commit used as an early warning for the
  forthcoming 1.18 API and schema.

Bootstrap and run either lane:

```bash
bash scripts/interop/bootstrap-tropy.sh stable
bash scripts/interop/run-live-tropy.sh stable

bash scripts/interop/bootstrap-tropy.sh canary
bash scripts/interop/run-live-tropy.sh canary
```

Before an OCR release or standalone build, run the combined live gate while
Tropy, Ollama, and LM Studio are available:

```bash
bash scripts/interop/run-live-release-gate.sh --publish-status
```

The gate auto-detects model servers on WSL localhost and its Windows-host
gateway. Model names are resolved from the servers by the same production
preflight used by the app; `ARTIFICE_LIVE_OLLAMA_MODEL` and
`ARTIFICE_LIVE_LM_STUDIO_MODEL` remain explicit overrides. It uses a disposable
Tropy profile/project, sends the repository's archival fixture scan through
both production OCR SDK paths, and publishes a commit status only after all
three applications pass. The executable workflow refuses to freeze OCR for a
commit without that status. `scripts/build-exe.sh artifice-ocr` runs the same
live gate locally before deleting old artifacts or invoking PyInstaller.

The bootstrap downloads a checksum-pinned Node runtime, checks out the pinned
Tropy revision, rebuilds Electron native modules, and creates Tropy's bundle.
Use `bash scripts/interop/doctor.sh stable` for a read-only diagnosis.

WSLg is sufficient for a local run. A headless Linux runner needs `xvfb`; the
runner automatically selects it when neither `DISPLAY` nor `WAYLAND_DISPLAY`
is present. `libvips-dev` is optional because Tropy can build against its
bundled libvips.

The npm audit output belongs to Tropy's isolated, ignored dependency tree. It
does not change Artifice's `package-lock.json` or Python lockfile. Do not run an
unreviewed `npm audit fix` in the upstream checkout: that would stop it being a
faithful build of the pinned release.

## Windows-native contract

WSL cannot prove Windows drive paths, SQLite URI spelling, or native file-lock
behaviour. Use a separate native Windows checkout of Artifice and a native
Windows Tropy source build, then run:

```powershell
.\scripts\interop\run-live-tropy.ps1 -Channel stable
```

To exercise a secondary drive, provide an existing temporary folder:

```powershell
.\scripts\interop\run-live-tropy.ps1 -Channel stable -TempRoot E:\ArtificeInterop
```

The PowerShell runner can test an installed Tropy executable while retaining
the source checkout for deterministic project creation:

```powershell
.\scripts\interop\run-live-tropy.ps1 `
  -TropySource C:\src\tropy `
  -TropyExecutable "C:\Program Files\Tropy\Tropy.exe"
```

Tropy's `node_modules` must be built on Windows. A WSL-built checkout contains
Linux native modules and cannot be reused by the Windows runner.

## Test selection and failure evidence

Normal `pytest` excludes `live_interop`; this keeps PR tests deterministic and
prevents accidental desktop launches. The wrapper sets the explicit environment
gate and runs only `apps/artifice-ocr/tests/test_tropy_live.py`.

On failure, pytest reports the temporary directory. Tropy's application log is
under `runtime/logs/tropy.log`, and captured stdout/stderr is
`runtime/process.log`. CI should upload that runtime directory when adding the
scheduled lane.

## Zotero boundary

Zotero is not yet an active Artifice integration, so there is no meaningful
live contract to automate yet. Before adding a Zotero process, record which
supported boundary the feature uses:

- the read-only desktop Local API for library and item selection;
- the HTTP citing protocol for citation insertion;
- the authenticated Web API for cloud writes; or
- a Zotero plugin when privileged local mutation is genuinely required.

Never test by editing `zotero.sqlite` directly. When implementation begins,
mirror the Tropy design: stable and beta binaries, isolated profiles/data,
mocked tests on every commit, and a real-process scheduled compatibility test.
