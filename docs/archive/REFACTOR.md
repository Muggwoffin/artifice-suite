# REFACTOR: Open-Source Compliance & Maintainability Plan

> **STATUS 2026-08-07 — All three items shipped, PR #62 merged to `main`.**
>
> Path validation (`packages/shared-ui/shared_ui/path_validation.py`), server bootstrap
> (`packages/shared-ui/shared_ui/server_bootstrap.py`), and legacy-data migration
> (`packages/secure-io/src/secure_io/migration.py`) are all complete and deployed.
> Full record, every deviation from this proposal, and all review findings:
> `docs/superpowers/plans/2026-08-07-refactor-oss-compliance.md`.
>
> **One deliberate structural deviation from this proposal's line 52:**
> `migration.py` defines **two** functions — `migrate_legacy_file` and
> `migrate_legacy_directory` — not the single `migrate_legacy_path()` this doc
> proposes. The three real call sites split cleanly into two shapes (single file
> vs. directory), and forcing them into one five-parameter function would have been
> the over-engineering this refactor exists to remove. Documented as a design call
> in the plan doc, §"Verified deviations" item 5.
>
> **One real security gap this refactor closed (not hypothetical — verified by a
> `security-auditor` pass):** `artifice-graph`'s `_validate_directory()`
> had no backslash normalisation and no POSIX Windows-drive-letter rejection before
> this work. It passed `raw` straight to `Path(raw)`, so a POSIX-hosted graph
> server could misinterpret `C:/Windows` as a relative path. `artifice-ocr` had
> both checks; graph did not. Consolidation made graph the stricter of the two.
> Plan doc §"Verified deviations" item 2.
>
> **Original proposal body — historical record, not current state.** The functions,
> paths, and figures below describe what was asked for. The plan doc above describes
> what was built and why it differs.

**Objective:** Improve open-source compliance, reduce duplication, and eliminate over-engineering without breaking existing functionality.

---

## 🔴 HIGH Priority (Security/Divergence Risks)

### 1. Consolidate Path Validation Logic
**Problem:** Duplicate implementations in `artifice-ocr` and `artifice-graph` with inconsistent security postures.
**Solution:**
- Create `packages/shared-ui/src/shared_ui/path_validation.py` with shared utilities:
  - `_normalise_path(raw: str, field_name: str) -> str`
  - `_build_allowed_roots(env_var: str) -> list[Path]`
  - `validate_path(raw: str, field_name: str, allowed_roots_env_var: str) -> str`
- Replace OCR’s `validation.py` and graph’s `_validate_directory()` with calls to the shared utility.
**Impact:** Eliminates 48 lines of duplicated code; ensures consistent security checks.
**Staggering:**
1. Implement `path_validation.py` (no breaking changes).
2. Update `artifice-ocr` to use the shared utility (backward-compatible).
3. Update `artifice-graph` to use the shared utility (backward-compatible).
4. Deprecate old implementations after validation.

---

### 2. Consolidate Server Bootstrap Logic
**Problem:** Identical `_free_port()`, `_wait_for_server()`, and `_start_server_thread()` in 3 apps.
**Solution:**
- Create `packages/shared-ui/src/shared_ui/server_bootstrap.py` with shared functions:
  - `free_port() -> int`
  - `port_available(port: int) -> bool`
  - `wait_for_server(port: int, timeout: float = 10.0) -> bool`
  - `start_server_thread(app, port: int) -> tuple[threading.Thread, list[BaseException]]`
  - `report_startup_failure(app_name: str, port: int, thread, errors: list[BaseException]) -> None`
  - `ensure_std_streams() -> None`
- Replace all 17 occurrences across `artifice-ocr`, `artifice-graph`, and `artifice-draft`.
**Impact:** Eliminates 120+ lines of duplicated code; prevents divergence in uvicorn error handling.
**Staggering:**
1. Implement `server_bootstrap.py` (no breaking changes).
2. Update `artifice-ocr` to use the shared utility (backward-compatible).
3. Update `artifice-graph` and `artifice-draft` in parallel (backward-compatible).
4. Deprecate old implementations after validation.

---

## 🟡 MEDIUM Priority (Maintenance Burden)

### 3. Consolidate Config Migration Logic
**Problem:** Three separate migration functions (`_migrate_legacy_db`, `_migrate_legacy_uploads`, `_resolve_user_data_dir`).
**Solution:**
- Create `packages/secure-io/src/secure_io/migration.py` with:
  - `migrate_legacy_path(legacy_path: Path, default_path: Path, user_override_signal: bool, collision_strategy: Literal["use_new", "use_legacy", "warn_both"], apply_restrictions: bool = False) -> Path`
- Replace app-specific implementations.
**Impact:** Reduces 150+ lines of duplicated code; ensures consistent security.
**Staggering:**
1. Implement `migration.py` (no breaking changes).
2. Update `artifice-transcribe` to use the shared utility (backward-compatible).
3. Update `artifice-graph` to use the shared utility (backward-compatible).
4. Deprecate old implementations after validation.

---

## 📌 Staggered Execution Plan

| Phase | Task | Apps Affected | Validation Steps |
|-------|------|---------------|------------------|
| 1 | Implement `path_validation.py` | None | Unit tests for shared utility |
| 2 | Update `artifice-ocr` path validation | `artifice-ocr` | Manual testing of file uploads/directory selection |
| 3 | Update `artifice-graph` path validation | `artifice-graph` | Manual testing of directory selection |
| 4 | Implement `server_bootstrap.py` | None | Unit tests for shared utility |
| 5 | Update `artifice-ocr` server bootstrap | `artifice-ocr` | Verify server starts on expected port |
| 6 | Update `artifice-graph` and `artifice-draft` server bootstrap | `artifice-graph`, `artifice-draft` | Verify server starts on expected port |
| 7 | Implement `migration.py` | None | Unit tests for shared utility |
| 8 | Update `artifice-transcribe` migrations | `artifice-transcribe` | Verify legacy data migration |
| 9 | Update `artifice-graph` migrations | `artifice-graph` | Verify legacy config migration |

---

## ✅ Validation Criteria
- **No breaking changes:** All apps must function identically post-refactor.
- **Backward compatibility:** Existing configurations and workflows must remain supported.
- **Test coverage:** Unit tests for shared utilities; manual validation for app-specific workflows.
- **Deprecation:** Old implementations marked as deprecated but left intact until validation is complete.

---

## 🚀 Next Steps
1. **Implement Phase 1:** Create `path_validation.py` and validate with unit tests.
2. **Implement Phase 2:** Update `artifice-ocr` to use the shared utility.
3. **Proceed sequentially:** Follow the staggered plan to minimize risk.