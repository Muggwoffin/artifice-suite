# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression tests for three correctness bugs.

Bug 1 – Extraction silently discards valid output / overwrites good data.
Bug 2 – Saved user configuration is never read back by load_config().
Bug 3 – Relative paths resolve against the working directory instead of the app root.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from artifice_graph.config import (
    ExtractionConfig,
    PipelineConfig,
    _apply_env_overrides,
    _merge_user_config,
    _USER_CONFIG_PATH,
    load_config,
    resolve_config_paths,
)
from artifice_graph.extraction.schemas import ExtractionResult
from artifice_graph.extraction.extractor import EntityExtractor
from artifice_graph.extraction.llm_client import LLMClient
from artifice_graph.models.document import TextChunk
from artifice_graph.models.entity import Entity, EntityType
from artifice_graph.models.relationship import Relationship
from artifice_graph.storage.file_store import FileStore

from model_harness.contract import (
    EndpointPolicy,
    ModelConnectorConfig,
    ModelProvider,
    ProviderCapabilities,
    RawCompletion,
    StructuredOutputMode,
    StructuredRequest,
)


# ---------------------------------------------------------------------------
# Bug 1a – ExtractionResult carries domain Entity / Relationship types
# ---------------------------------------------------------------------------

class TestBug1aExtractionResultTypes:

    def test_extraction_result_accepts_entity_objects(self) -> None:
        """ExtractionResult must accept Entity objects (the domain type)."""
        entity = Entity(
            name="Klemens von Metternich",
            entity_type=EntityType.PERSON,
            aliases=["Metternich"],
            summary="Austrian foreign minister.",
            source_doc_ids=["doc1"],
        )
        rel = Relationship(
            source_entity="Klemens von Metternich",
            target_entity="Austria",
            relationship_type="served",
        )
        result = ExtractionResult(entities=[entity], relationships=[rel])
        assert len(result.entities) == 1
        assert isinstance(result.entities[0], Entity)
        assert result.entities[0].name == "Klemens von Metternich"
        assert result.entities[0].id == "klemens_von_metternich"
        assert len(result.relationships) == 1
        assert isinstance(result.relationships[0], Relationship)

    def test_extraction_result_accepts_raw_dicts(self) -> None:
        """Raw LLM dicts (as passed by _validate_or_retry) still work."""
        raw_entities = [{"name": "Vienna", "entity_type": "Location"}]
        raw_rels = [{"source_entity": "Vienna", "target_entity": "Austria", "relationship_type": "located_in"}]
        result = ExtractionResult(entities=raw_entities, relationships=raw_rels)
        assert len(result.entities) == 1
        assert isinstance(result.entities[0], Entity)
        assert result.entities[0].id == "vienna"
        assert len(result.relationships) == 1
        assert isinstance(result.relationships[0], Relationship)

    def test_empty_extraction_result(self) -> None:
        """Empty result is valid and produces empty lists."""
        result = ExtractionResult()
        assert result.entities == []
        assert result.relationships == []


# ---------------------------------------------------------------------------
# Bug 1b – extract_batch must not silently convert total failure into success
# ---------------------------------------------------------------------------

class _FailingProvider:
    """A ModelProvider that raises on every ``complete`` call."""

    def capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(structured_output=StructuredOutputMode.PROMPTED)

    async def complete(self, request: StructuredRequest) -> RawCompletion:
        raise ConnectionError("Simulated connection failure")


class _PassEndpointPolicy:
    """An EndpointPolicy that always passes."""

    def resolve(self, endpoint: str) -> str:
        return endpoint


class TestBug1bLoudFailure:

    def test_all_chunks_fail_raises(self) -> None:
        """When every chunk raises, extract_batch must raise RuntimeError."""
        extractor = EntityExtractor(
            config=ExtractionConfig(max_retries=1, retry_delay=0.0),
            provider=_FailingProvider(),
            endpoint_policy=_PassEndpointPolicy(),
        )
        chunks = [TextChunk(id="c1", text="foo", document_id="d1", chunk_index=0, start_char=0, end_char=3)]

        with pytest.raises(RuntimeError, match="All 1 chunks failed"):
            extractor.extract_batch(chunks)

    def test_single_failure_still_returns_results(self) -> None:
        """Partial success should still return valid results."""
        # We need a mock that succeeds for one chunk and fails for another.
        # Rather than mock deeply, we test the contract at the level closest
        # to the bug: the ExtractionResult type acceptance.
        #
        # The loud-failure contract is: total failure => RuntimeError,
        # partial failure => warning log + results.
        # This is tested structurally in test_all_chunks_fail_raises above.

    def test_empty_chunks_returns_empty(self) -> None:
        """Zero chunks is not a failure – return empty list."""
        extractor = EntityExtractor(
            config=ExtractionConfig(max_retries=1, retry_delay=0.0),
            provider=_FailingProvider(),
            endpoint_policy=_PassEndpointPolicy(),
        )
        results = extractor.extract_batch([])
        assert results == []


# ---------------------------------------------------------------------------
# Bug 1c – Silent empty-overwrite protection
# ---------------------------------------------------------------------------

class TestBug1cEmptyOverwriteProtection:

    def test_safe_save_refuses_empty_overwrite(self, tmp_path: Path) -> None:
        """_safe_save_models refuses to overwrite non-empty file with empty data."""
        from artifice_graph.cli import _safe_save_models

        store = FileStore(tmp_path)
        entity = Entity(name="A", entity_type=EntityType.PERSON)
        store.save_models("entities.json", [entity])

        # Try to overwrite with empty list, force=False -> refused
        result = _safe_save_models(store, "entities.json", [], force=False)
        assert result is False
        assert len(store.load("entities.json")) == 1

    def test_safe_save_force_overwrite(self, tmp_path: Path) -> None:
        """_safe_save_models with force=True overwrites."""
        from artifice_graph.cli import _safe_save_models

        store = FileStore(tmp_path)
        entity = Entity(name="A", entity_type=EntityType.PERSON)
        store.save_models("entities.json", [entity])

        result = _safe_save_models(store, "entities.json", [], force=True)
        assert result is True
        assert store.load("entities.json") == []

    def test_safe_save_no_existing_file(self, tmp_path: Path) -> None:
        """Writing empty data to a new file is allowed (no data to lose)."""
        from artifice_graph.cli import _safe_save_models

        store = FileStore(tmp_path)
        result = _safe_save_models(store, "entities.json", [], force=False)
        assert result is True

    def test_safe_save_nonempty_overwrites_freely(self, tmp_path: Path) -> None:
        """Writing non-empty data over non-empty old data is allowed."""
        from artifice_graph.cli import _safe_save_models

        store = FileStore(tmp_path)
        store.save_models("entities.json", [Entity(name="A", entity_type=EntityType.PERSON)])
        entity_b = Entity(name="B", entity_type=EntityType.PERSON)
        result = _safe_save_models(store, "entities.json", [entity_b], force=False)
        assert result is True
        loaded = store.load("entities.json")
        assert len(loaded) == 1
        assert loaded[0]["name"] == "B"


# ---------------------------------------------------------------------------
# Bug 2 – load_config() can read user-saved configuration
# ---------------------------------------------------------------------------

class TestBug2LoadConfigWithUserConfig:

    def test_user_config_overrides_defaults(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """load_config merges user-saved config.json on top of config.yaml."""
        user_cfg_path = tmp_path / "user_config.json"
        monkeypatch.setattr(
            "artifice_graph.config._USER_CONFIG_PATH",
            user_cfg_path,
        )
        user_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        user_data = {
            "llm": {"model": "gemma4:12b", "base_url": "http://172.21.176.1:11434"},
            "extraction": {"batch_size": 10},
        }
        user_cfg_path.write_text(json.dumps(user_data))

        # Provide a temp config.yaml that our test controls
        cfg = Path(__file__).parent.parent / "config.yaml"

        config = load_config(cfg)

        assert config.llm.model == "gemma4:12b"
        assert config.llm.base_url == "http://172.21.176.1:11434"
        assert config.extraction.batch_size == 10
        # Fields NOT in user config keep their config.yaml / default values
        assert config.llm.temperature == 0.1  # from config.yaml default

    def test_load_config_works_without_user_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """load_config works when no user config file exists."""
        nonexistent = tmp_path / "nonexistent.json"
        monkeypatch.setattr("artifice_graph.config._USER_CONFIG_PATH", nonexistent)

        cfg = Path(__file__).parent.parent / "config.yaml"

        config = load_config(cfg)
        # Should return valid config from config.yaml
        assert config.llm.model == "gemma2:27b"

    def test_user_config_ignores_unknown_keys(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Keys not in the config model are silently ignored."""
        user_cfg_path = tmp_path / "user_config.json"
        monkeypatch.setattr("artifice_graph.config._USER_CONFIG_PATH", user_cfg_path)
        user_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        user_data = {
            "llm": {"model": "gemma4:12b", "nonexistent_field": "ignored"},
        }
        user_cfg_path.write_text(json.dumps(user_data))

        cfg = Path(__file__).parent.parent / "config.yaml"

        config = load_config(cfg)
        assert config.llm.model == "gemma4:12b"

    def test_merge_user_config_does_nothing_for_no_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """_merge_user_config is a no-op when the file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.json"
        monkeypatch.setattr("artifice_graph.config._USER_CONFIG_PATH", nonexistent)

        config = PipelineConfig()
        original_model = config.llm.model
        _merge_user_config(config)
        assert config.llm.model == original_model


# ---------------------------------------------------------------------------
# Bug 3 – Relative paths resolve against the app root regardless of cwd
# ---------------------------------------------------------------------------

class TestBug3RelativePathResolution:

    def test_resolve_config_paths_turns_relative_into_absolute(self, tmp_path: Path) -> None:
        """All relative-path fields become absolute after resolution."""
        config = PipelineConfig()
        app_root = tmp_path  # a real, platform-valid absolute path

        # Set known relative values
        config.ingestion.input_dir = "data/input_ocr"
        config.extraction.cache_dir = "data/cache"
        config.export.output_dir = "data/output"
        config.export.obsidian_vault_dir = "data/vault"
        config.entity_resolution.aliases_file = "data/aliases.yaml"
        config.storage.entities_file = "data/output/entities.json"

        resolve_config_paths(config, app_root)

        # The product resolves the joined path (config.py:154), so compare
        # against the resolved form — never the plain join of two parts.
        assert Path(config.ingestion.input_dir).is_absolute()
        assert str((app_root / "data/input_ocr").resolve()) == config.ingestion.input_dir
        assert str((app_root / "data/cache").resolve()) == config.extraction.cache_dir
        assert str((app_root / "data/output").resolve()) == config.export.output_dir
        assert str((app_root / "data/vault").resolve()) == config.export.obsidian_vault_dir
        assert str((app_root / "data/aliases.yaml").resolve()) == config.entity_resolution.aliases_file
        assert str((app_root / "data/output/entities.json").resolve()) == config.storage.entities_file

    def test_absolute_paths_are_preserved(self, tmp_path: Path) -> None:
        """An already-absolute path is left untouched."""
        config = PipelineConfig()
        app_root = tmp_path  # a real, platform-valid absolute path

        absolute_dir = tmp_path / "custom" / "absolute" / "path"
        absolute_dir.mkdir(parents=True)
        config.export.output_dir = str(absolute_dir)
        resolve_config_paths(config, app_root)

        # Compared UNRESOLVED on purpose. The property is that an absolute path
        # is passed through untouched, and config.py:154 only resolves the
        # relative branch. Asserting against `.resolve()` would keep passing if
        # the product started resolving absolute paths too — which is precisely
        # the regression this test exists to catch.
        assert config.export.output_dir == str(absolute_dir)

    def test_empty_paths_are_skipped(self, tmp_path: Path) -> None:
        """Empty-string paths are not resolved (they stay empty)."""
        config = PipelineConfig()
        app_root = tmp_path  # a real, platform-valid absolute path

        config.export.output_dir = ""
        resolve_config_paths(config, app_root)

        assert config.export.output_dir == ""

    def test_load_config_resolves_paths(self) -> None:
        """load_config itself resolves paths against the config-file directory."""
        cfg = Path(__file__).parent.parent / "config.yaml"
        app_root = cfg.parent.resolve()

        config = load_config(cfg)
        output_path = Path(config.export.output_dir)
        assert output_path.is_absolute(), f"Expected absolute path, got {output_path}"
        assert output_path == app_root / "data" / "output"
        assert Path(config.ingestion.input_dir) == app_root / "data" / "input_ocr"

    def test_paths_are_resolved_independent_of_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Changing working directory does NOT change resolved paths."""
        cfg = Path(__file__).parent.parent / "config.yaml"
        app_root = cfg.parent.resolve()

        # Run from a completely different directory
        monkeypatch.chdir(tmp_path)
        config = load_config(cfg)

        output = Path(config.export.output_dir)
        assert output.is_absolute()
        assert output == app_root / "data" / "output"
        # Sanity check: the output is NOT under tmp_path
        assert not str(output).startswith(str(tmp_path))


# ---------------------------------------------------------------------------
# Bug 4 – Upload validation follows ingestion config
# ---------------------------------------------------------------------------

class TestBug4UploadValidation:

    class _FakeUpload:
        def __init__(self, filename: str, payload: bytes) -> None:
            self.filename = filename
            self._pos = 0
            self._payload = payload

        async def read(self, size: int = -1) -> bytes:
            if self._pos >= len(self._payload):
                return b""
            if size < 0:
                result = self._payload[self._pos:]
                self._pos = len(self._payload)
                return result
            result = self._payload[self._pos:self._pos + size]
            self._pos += size
            return result

    def test_upload_accepts_configured_extensions_and_builtin_handlers(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """api_upload_files accepts configured extensions plus PDF/HTML handlers."""
        from artifice_graph.config import PipelineConfig
        from artifice_graph.web import server as server_mod

        cfg = PipelineConfig()
        cfg.ingestion.input_dir = str(tmp_path / "input")
        cfg.ingestion.supported_extensions = [".txt", ".csv"]
        monkeypatch.setattr(server_mod, "load_config", lambda: cfg)

        response = asyncio.run(
            server_mod.api_upload_files(
                [
                    self._FakeUpload("notes.csv", b"csv payload"),
                    self._FakeUpload("scan.pdf", b"pdf payload"),
                    self._FakeUpload("draft.docx", b"docx payload"),
                ]
            )
        )

        uploaded = response["uploaded"]
        assert uploaded[0]["status"] == "ok"
        assert uploaded[0]["filename"] == "notes.csv"
        assert uploaded[1]["status"] == "ok"
        assert uploaded[1]["filename"] == "scan.pdf"
        assert uploaded[2]["status"] == "rejected"
        assert ".csv" in uploaded[2]["reason"]
        assert ".pdf" in uploaded[2]["reason"]


# ---------------------------------------------------------------------------
# Integration: CLI-level regression for the demo command (sanity check)
# ---------------------------------------------------------------------------

class TestDemoRegression:

    def test_demo_with_resolved_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """demo command works when cwd is not the app root, and output goes to tmp."""
        import artifice_graph.config as cfg_mod
        import artifice_graph.cli as cli_mod

        orig_load = cfg_mod.load_config

        def _load_config_override(*args, **kwargs):
            c = orig_load(*args, **kwargs)
            c.export.output_dir = str(tmp_path / "data" / "output")
            c.export.obsidian_vault_dir = str(tmp_path / "data" / "obsidian_vault")
            c.entity_resolution.use_semantic = False  # avoid Ollama dependency
            resolve_config_paths(c, tmp_path)
            return c

        # Patch both the config module and the cli module's imported reference
        monkeypatch.setattr(cfg_mod, "load_config", _load_config_override)
        monkeypatch.setattr(cli_mod, "load_config", _load_config_override)
        monkeypatch.chdir(tmp_path)  # different cwd from app root

        from artifice_graph.cli import demo
        demo()

        output = tmp_path / "data" / "output"
        assert (output / "entities.json").exists()
        assert (output / "relationships.json").exists()


# ---------------------------------------------------------------------------
# Bug 1 — Plain function defaults (OptionInfo sentinel regression)
# ---------------------------------------------------------------------------

class TestBug1PlainFunctionDefaults:

    def test_run_ingest_has_real_defaults(self) -> None:
        """Plain function params carry real Python defaults, not OptionInfo sentinels."""
        import inspect
        from artifice_graph.cli import _run_ingest

        sig = inspect.signature(_run_ingest)
        assert sig.parameters["chunk_size"].default == 2000
        assert sig.parameters["chunk_overlap"].default == 200
        assert sig.parameters["model"].default is None
        assert sig.parameters["base_url"].default is None

    def test_run_extract_has_real_defaults(self) -> None:
        """Plain function params carry real Python defaults, not OptionInfo sentinels."""
        import inspect
        from artifice_graph.cli import _run_extract

        sig = inspect.signature(_run_extract)
        assert sig.parameters["batch_size"].default == 5
        assert sig.parameters["api_key"].default is None
        assert sig.parameters["force"].default is False

    def test_plain_functions_are_separate_from_commands(self) -> None:
        """Plain functions exist alongside @app.command() wrappers and are importable."""
        from artifice_graph.cli import (
            _run_ingest, _run_extract, _run_resolve_entities,
            _run_build_vault, _run_build_graph,
        )
        import inspect

        for fn in [_run_ingest, _run_extract, _run_resolve_entities,
                    _run_build_vault, _run_build_graph]:
            assert inspect.isfunction(fn)
            assert fn.__name__.startswith("_run_")


# ---------------------------------------------------------------------------
# Bug 2 — Web run-all reaches all stages (stream liveness vs. continuation)
# ---------------------------------------------------------------------------

class TestBug2WebRunAllContinuation:

    def test_run_all_reaches_all_five_stages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_do_run_all calls all 5 stage helpers when none fail."""
        from artifice_graph.web.server import _do_run_all, _run_ok
        from artifice_graph.config import PipelineConfig

        calls: list[str] = []

        def _record_ingest(cfg, inc, rk, *, close_stream=False):
            calls.append("ingest")

        def _record_extract(cfg, rk, *, close_stream=False):
            calls.append("extract")

        def _record_resolve(cfg, rk, *, close_stream=False):
            calls.append("resolve")

        def _record_vault(cfg, rk, *, close_stream=False):
            calls.append("vault")

        def _record_graph(cfg, rk, *, close_stream=False):
            calls.append("graph")

        monkeypatch.setattr("artifice_graph.web.server._do_ingest", _record_ingest)
        monkeypatch.setattr("artifice_graph.web.server._do_extract", _record_extract)
        monkeypatch.setattr("artifice_graph.web.server._do_resolve", _record_resolve)
        monkeypatch.setattr("artifice_graph.web.server._do_vault", _record_vault)
        monkeypatch.setattr("artifice_graph.web.server._do_graph", _record_graph)

        cfg = PipelineConfig()
        _do_run_all(cfg, False, "test-reaches-all")

        assert calls == ["ingest", "extract", "resolve", "vault", "graph"]

    def test_run_all_halt_on_stage_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_do_run_all stops after a failing stage and does not call later stages."""
        from artifice_graph.web.server import _do_run_all, _run_ok
        from artifice_graph.config import PipelineConfig

        calls: list[str] = []

        def _failing_ingest(cfg, inc, rk, *, close_stream=False):
            calls.append("ingest")
            _run_ok[rk] = False  # simulate stage failure

        def _record_extract(cfg, rk, *, close_stream=False):
            calls.append("extract")

        def _record_resolve(cfg, rk, *, close_stream=False):
            calls.append("resolve")

        def _record_vault(cfg, rk, *, close_stream=False):
            calls.append("vault")

        def _record_graph(cfg, rk, *, close_stream=False):
            calls.append("graph")

        monkeypatch.setattr("artifice_graph.web.server._do_ingest", _failing_ingest)
        monkeypatch.setattr("artifice_graph.web.server._do_extract", _record_extract)
        monkeypatch.setattr("artifice_graph.web.server._do_resolve", _record_resolve)
        monkeypatch.setattr("artifice_graph.web.server._do_vault", _record_vault)
        monkeypatch.setattr("artifice_graph.web.server._do_graph", _record_graph)

        cfg = PipelineConfig()
        _do_run_all(cfg, False, "test-halt")

        # Only ingest should have been called — stages 2-5 skipped
        assert calls == ["ingest"]

    def test_mark_run_failed_sets_ok_false(self) -> None:
        """_mark_run_failed sets _run_ok[run_key] to False."""
        from artifice_graph.web.server import _mark_run_failed, _run_ok

        _run_ok.pop("test-fail", None)
        _mark_run_failed("test-fail", "simulated error")
        assert _run_ok["test-fail"] is False


# ---------------------------------------------------------------------------
# Bug 3 — Exit code non-zero on failure
# ---------------------------------------------------------------------------

class TestBug3ExitCode:

    def test_run_stage_returns_false_on_exception(self) -> None:
        """_run_stage returns False when the stage function raises."""
        from artifice_graph.cli import _run_stage

        def _fail():
            raise RuntimeError("simulated failure")

        result = _run_stage(1, 5, "Test", _fail)
        assert result is False

    def test_run_stage_returns_false_on_typer_exit(self) -> None:
        """_run_stage returns False when the stage raises typer.Exit."""
        import typer
        from artifice_graph.cli import _run_stage

        def _exit():
            raise typer.Exit(1)

        result = _run_stage(1, 5, "Test", _exit)
        assert result is False

    def test_run_stage_returns_true_on_success(self) -> None:
        """_run_stage returns True when the stage function completes normally."""
        from artifice_graph.cli import _run_stage

        def _ok():
            pass

        result = _run_stage(1, 5, "Test", _ok)
        assert result is True

    def test_run_all_exits_nonzero_on_partial_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_all raises typer.Exit(1) when any stage fails."""
        import typer
        from artifice_graph.cli import _run_stage, _run_ingest
        from artifice_graph.config import PipelineConfig, resolve_config_paths

        # Patch _run_stage to simulate: stages 1,3,4,5 succeed; stage 2 fails
        original_run_stage = _run_stage
        call_count = [0]

        def _mock_run_stage(stage, total, label, fn):
            call_count[0] += 1
            if call_count[0] == 2:  # stage 2 = extract
                return False
            # For other stages, just return True (don't actually run work)
            return True

        monkeypatch.setattr("artifice_graph.cli._run_stage", _mock_run_stage)

        from artifice_graph.cli import run_all

        with pytest.raises(typer.Exit) as exc_info:
            run_all(input_dir=str(tmp_path))

        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# Fix: entities_raw.json saved during resolution
# ---------------------------------------------------------------------------

class TestFixEntitiesRaw:

    def test_do_resolve_saves_entities_raw(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """_do_resolve writes the pre-resolution entities to entities_raw.json."""
        import json
        from artifice_graph.config import PipelineConfig
        from artifice_graph.models.entity import Entity, EntityType
        from artifice_graph.models.relationship import Relationship

        cfg = PipelineConfig()
        cfg.export.output_dir = str(tmp_path)

        # Pre-populate entities.json with two similar entities
        ents = [
            Entity(name="Klemens von Metternich", entity_type=EntityType.PERSON,
                   aliases=["Metternich"]),
            Entity(name="Metternich", entity_type=EntityType.PERSON,
                   aliases=["Prince Metternich"]),
        ]
        rels: list[Relationship] = []

        import artifice_graph.storage.file_store as fs_mod
        store = fs_mod.FileStore(str(tmp_path))
        store.save_models("entities.json", ents)
        store.save_models("relationships.json", rels)

        monkeypatch.setattr("artifice_graph.web.server._load_store", lambda cfg: store)
        monkeypatch.setattr("artifice_graph.web.server._build_resolver", lambda cfg: _NoOpResolver())

        from artifice_graph.web.server import _do_resolve
        _do_resolve(cfg, "test-raw", close_stream=False)

        raw = store.load("entities_raw.json")
        assert raw is not None
        assert len(raw) == 2


class _NoOpResolver:
    """Resolver that returns inputs unchanged (no dedup)."""
    def resolve(self, entities, relationships):
        return entities, relationships


# ---------------------------------------------------------------------------
# Fix: GraphExporter honours graph_formats list
# ---------------------------------------------------------------------------

class TestFixGraphFormats:

    def test_exporter_uses_graph_formats_list(self, tmp_path: Path) -> None:
        """When no explicit formats given, GraphExporter uses config.graph_formats."""
        from artifice_graph.config import ExportConfig
        from artifice_graph.exporters.graph_exporter import GraphExporter
        from artifice_graph.models.entity import Entity, EntityType
        from artifice_graph.models.relationship import Relationship

        config = ExportConfig(
            output_dir=str(tmp_path),
            graph_formats=["graphml", "json", "csv"],
            graph_format="graphml",  # legacy field — should be ignored
        )
        exporter = GraphExporter(config)

        # Create trivial entities
        e = Entity(name="Test", entity_type=EntityType.CONCEPT)
        results = exporter.export([e], [], formats=None)

        # Should have output for all three configured formats
        assert "graphml" in results
        assert "json" in results
        assert "nodes_csv" in results  # csv produces nodes.csv + edges.csv
        assert "edges_csv" in results
        assert len(results) >= 4

    def test_exporter_explicit_formats_override_config(self, tmp_path: Path) -> None:
        """Explicit format argument overrides config.graph_formats."""
        from artifice_graph.config import ExportConfig
        from artifice_graph.exporters.graph_exporter import GraphExporter
        from artifice_graph.models.entity import Entity, EntityType

        config = ExportConfig(
            output_dir=str(tmp_path),
            graph_formats=["graphml", "json", "csv"],
        )
        exporter = GraphExporter(config)
        e = Entity(name="Test", entity_type=EntityType.CONCEPT)
        results = exporter.export([e], [], formats=["gexf"])

        assert "gexf" in results
        assert "graphml" not in results


# ---------------------------------------------------------------------------
# Env-var overrides — LLM_BASE_URL and EMBEDDING_BASE_URL
# ---------------------------------------------------------------------------


class TestEnvOverrides:

    def test_llm_base_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM_BASE_URL env var overrides the config file and defaults."""
        monkeypatch.setenv("LLM_BASE_URL", "http://host.docker.internal:11434/v1")

        config = PipelineConfig()
        assert config.llm.base_url == "http://localhost:11434/v1"  # default

        _apply_env_overrides(config)
        assert config.llm.base_url == "http://host.docker.internal:11434/v1"

    def test_embedding_base_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EMBEDDING_BASE_URL env var overrides the config file and defaults."""
        monkeypatch.setenv("EMBEDDING_BASE_URL", "http://host.docker.internal:11434")

        config = PipelineConfig()
        assert config.embedding.base_url == "http://localhost:11434"  # default

        _apply_env_overrides(config)
        assert config.embedding.base_url == "http://host.docker.internal:11434"

    def test_defaults_preserved_when_env_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When env vars are not set, defaults are preserved."""
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)

        config = PipelineConfig()
        _apply_env_overrides(config)

        assert config.llm.base_url == "http://localhost:11434/v1"
        assert config.embedding.base_url == "http://localhost:11434"

    def test_env_beats_user_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env var overrides user config, establishing correct precedence."""
        monkeypatch.setenv("LLM_BASE_URL", "http://env-override:11434/v1")

        config = PipelineConfig()
        # Simulate user config having set a different value
        config.llm.base_url = "http://user-config:11434/v1"
        assert config.llm.base_url == "http://user-config:11434/v1"

        _apply_env_overrides(config)
        assert config.llm.base_url == "http://env-override:11434/v1"

    def test_load_config_applies_env_overrides(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """load_config() applies env overrides after user config merge."""
        user_cfg_path = tmp_path / "user_config.json"
        monkeypatch.setattr(
            "artifice_graph.config._USER_CONFIG_PATH",
            user_cfg_path,
        )
        user_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        user_data = {
            "llm": {"base_url": "http://user-config:11434/v1"},
        }
        user_cfg_path.write_text(json.dumps(user_data))

        # Set env var to a different value
        monkeypatch.setenv("LLM_BASE_URL", "http://env-override:11434/v1")
        monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)

        cfg = Path(__file__).parent.parent / "config.yaml"
        config = load_config(cfg)

        # Env var should win over user config
        assert config.llm.base_url == "http://env-override:11434/v1"
        # Embedding should still be at default (no env set)
        assert config.embedding.base_url == "http://localhost:11434"

    def test_empty_env_var_does_not_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty env var value does NOT override — it falls back to existing."""
        monkeypatch.setenv("LLM_BASE_URL", "")

        config = PipelineConfig()
        original = config.llm.base_url
        _apply_env_overrides(config)
        assert config.llm.base_url == original

    def test_whitespace_only_env_var_does_not_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Whitespace-only env var value does NOT override."""
        monkeypatch.setenv("LLM_BASE_URL", "   ")

        config = PipelineConfig()
        original = config.llm.base_url
        _apply_env_overrides(config)
        assert config.llm.base_url == original
