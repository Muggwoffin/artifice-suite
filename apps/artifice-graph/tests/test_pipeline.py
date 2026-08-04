# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration test for the Graph Pipeline — no LLM required.

Tests chunking, entity resolution, graph export, and Obsidian vault build
using synthetically constructed entities and relationships.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from artifice_graph.config import (
    ExportConfig,
    IngestionConfig,
    PipelineConfig,
    load_config,
    resolve_config_paths,
)
from artifice_graph.entity_resolution.resolver import EntityResolver
from artifice_graph.exporters.graph_exporter import GraphExporter
from artifice_graph.exporters.obsidian_exporter import ObsidianExporter
from artifice_graph.ingestion.chunker import TextChunker
from artifice_graph.models.document import Document, TextChunk
from artifice_graph.models.entity import Entity, EntityType
from artifice_graph.models.relationship import Relationship
from artifice_graph.storage.file_store import FileStore


SAMPLE_TEXT = (
    "The Congress of Vienna was convened in 1814 to reconstruct Europe after the "
    "Napoleonic Wars. Prince Klemens von Metternich, the Austrian foreign minister, "
    "played a central role in the negotiations. Tsar Alexander I of Russia sought to "
    "expand Russian influence across the continent. The resulting Concert of Europe "
    "established a balance of power that lasted for decades."
)


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "output"


@pytest.fixture
def sample_entities() -> list[Entity]:
    return [
        Entity(
            name="Klemens von Metternich",
            entity_type=EntityType.PERSON,
            aliases=["Metternich"],
            summary="Austrian foreign minister at the Congress of Vienna.",
            source_doc_ids=["congress_of_vienna"],
        ),
        Entity(
            name="Alexander I",
            entity_type=EntityType.PERSON,
            aliases=["Tsar Alexander I"],
            summary="Tsar of Russia who sought expanded influence.",
            source_doc_ids=["congress_of_vienna"],
        ),
        Entity(
            name="Congress of Vienna",
            entity_type=EntityType.EVENT,
            aliases=["The Congress"],
            summary="Diplomatic conference of 1814-1815 to reorganize Europe.",
            source_doc_ids=["congress_of_vienna"],
        ),
        Entity(
            name="Austria",
            entity_type=EntityType.LOCATION,
            aliases=[],
            summary="Host nation of the Congress of Vienna.",
            source_doc_ids=["congress_of_vienna"],
        ),
        Entity(
            name="Russia",
            entity_type=EntityType.LOCATION,
            aliases=[],
            summary="Major European power at the Congress.",
            source_doc_ids=["congress_of_vienna"],
        ),
        Entity(
            name="Concert of Europe",
            entity_type=EntityType.CONCEPT,
            aliases=[],
            summary="Balance-of-power system after the Congress.",
            source_doc_ids=["congress_of_vienna"],
        ),
    ]


@pytest.fixture
def sample_relationships() -> list[Relationship]:
    return [
        Relationship(
            source_entity="Klemens von Metternich",
            target_entity="Congress of Vienna",
            relationship_type="participated_in",
            time_frame="1814-1815",
            evidence_quote="played a central role in the negotiations",
            confidence_score=0.95,
        ),
        Relationship(
            source_entity="Alexander I",
            target_entity="Russia",
            relationship_type="ruled",
            time_frame="1801-1825",
            evidence_quote="Tsar Alexander I of Russia",
            confidence_score=0.95,
        ),
        Relationship(
            source_entity="Congress of Vienna",
            target_entity="Concert of Europe",
            relationship_type="established",
            time_frame="1815",
            evidence_quote="The resulting Concert of Europe established a balance of power",
            confidence_score=0.95,
        ),
    ]


class TestChunker:
    def test_chunk_basic(self) -> None:
        chunker = TextChunker(
            IngestionConfig(chunk_size=100, chunk_overlap=20, input_dir=".")
        )
        doc = Document(
            id="test_doc",
            filename="test.txt",
            filepath="<test>",
            raw_text=SAMPLE_TEXT,
        )
        chunks = chunker.chunk_document(doc)
        assert len(chunks) > 1
        assert chunks[0].document_id == "test_doc"
        assert all(c.text for c in chunks)

    def test_ingest_string(self) -> None:
        chunker = TextChunker()
        chunk = chunker.ingest_string("Hello world", doc_id="inline")
        assert chunk.id == "inline__chunk_0000"
        assert chunk.text == "Hello world"


class TestEntityResolution:
    def test_deduplication(self) -> None:
        entities = [
            Entity(name="Klemens Metternich", entity_type=EntityType.PERSON, aliases=[], summary="Short"),
            Entity(
                name="Klemens von Metternich",
                entity_type=EntityType.PERSON,
                aliases=["Prince Metternich"],
                summary="Longer summary about the Austrian statesman and diplomat.",
                source_doc_ids=["doc1"],
            ),
        ]
        relationships = [
            Relationship(
                source_entity="Klemens Metternich",
                target_entity="Austria",
                relationship_type="served",
            )
        ]

        from artifice_graph.config import EntityResolutionConfig
        resolver = EntityResolver(EntityResolutionConfig(similarity_threshold=0.85))
        merged, updated_rels = resolver.resolve(entities, relationships)

        assert len(merged) == 1
        assert merged[0].name == "Klemens Metternich"
        assert "Prince Metternich" in merged[0].aliases
        assert updated_rels[0].source_entity == "Klemens Metternich"

    def test_no_merge(self) -> None:
        entities = [
            Entity(name="Metternich", entity_type=EntityType.PERSON),
            Entity(name="Wellington", entity_type=EntityType.PERSON),
        ]
        resolver = EntityResolver()
        merged, _ = resolver.resolve(entities, [])
        assert len(merged) == 2


class TestGraphExporter:
    def test_export(self, tmp_output: Path, sample_entities: list[Entity], sample_relationships: list[Relationship]) -> None:
        config = ExportConfig(output_dir=str(tmp_output), graph_format="graphml")
        exporter = GraphExporter(config)
        results = exporter.export(sample_entities, sample_relationships, formats=["graphml", "json", "gexf", "csv"])

        assert "graphml" in results
        assert "json" in results
        assert "gexf" in results
        assert results["graphml"].exists()
        assert results["json"].exists()
        assert results["gexf"].exists()
        assert results["nodes_csv"].exists()
        assert results["edges_csv"].exists()
        assert exporter.store.node_count == len(sample_entities)
        assert exporter.store.edge_count == len(sample_relationships)

    def test_gexf_viz_attributes(self, tmp_output: Path, sample_entities: list[Entity], sample_relationships: list[Relationship]) -> None:
        config = ExportConfig(output_dir=str(tmp_output), graph_format="gexf")
        exporter = GraphExporter(config)
        results = exporter.export(sample_entities, sample_relationships, formats=["gexf"])
        gexf_path = results["gexf"]
        content = gexf_path.read_text(encoding="utf-8")
        assert "viz:color" in content
        assert "viz:size" in content
        assert content.count("<node ") <= len(sample_entities)


class TestObsidianExporter:
    def test_vault_structure(
        self,
        tmp_output: Path,
        sample_entities: list[Entity],
        sample_relationships: list[Relationship],
    ) -> None:
        vault_dir = tmp_output / "vault"
        config = ExportConfig(obsidian_vault_dir=str(vault_dir), output_dir=str(tmp_output))

        doc = Document(
            id="congress_of_vienna",
            filename="congress_of_vienna.txt",
            filepath="<test>",
            raw_text=SAMPLE_TEXT,
        )
        chunker = TextChunker(IngestionConfig(chunk_size=2000, chunk_overlap=0, input_dir="."))
        chunk = chunker.ingest_string(SAMPLE_TEXT, doc_id="congress_of_vienna")
        chunks = [chunk]

        resolver = EntityResolver()
        merged, updated_rels = resolver.resolve(sample_entities, sample_relationships)

        exporter = ObsidianExporter(resolver, config)
        vault_path = exporter.build_vault(merged, updated_rels, [doc], chunks)

        assert vault_path.exists()
        assert (vault_path / "01_Sources").exists()
        assert (vault_path / "02_Entities" / "Persons").exists()
        assert (vault_path / "02_Entities" / "Locations").exists()
        assert (vault_path / "02_Entities" / "Events").exists()
        assert (vault_path / "02_Entities" / "Concepts").exists()
        assert (vault_path / "02_Entities" / "Organizations").exists()

        person_notes = list((vault_path / "02_Entities" / "Persons").glob("*.md"))
        assert len(person_notes) == 2

        source_notes = list((vault_path / "01_Sources").glob("*.md"))
        assert len(source_notes) == 1

    def test_wikilinks_in_entity_notes(self, tmp_output: Path) -> None:
        vault_dir = tmp_output / "vault2"
        config = ExportConfig(obsidian_vault_dir=str(vault_dir), output_dir=str(tmp_output))

        entities = [
            Entity(
                name="Metternich",
                entity_type=EntityType.PERSON,
                aliases=[],
                summary="Austrian statesman.",
                source_doc_ids=["src1"],
            ),
            Entity(
                name="Austria",
                entity_type=EntityType.LOCATION,
                aliases=[],
                summary="European nation.",
                source_doc_ids=["src1"],
            ),
        ]
        relationships = [
            Relationship(
                source_entity="Metternich",
                target_entity="Austria",
                relationship_type="served",
                time_frame="1809-1848",
                evidence_quote="the Austrian foreign minister",
            )
        ]

        exporter = ObsidianExporter(config=config)
        vault_path = exporter.build_vault(entities, relationships)

        mett_note = (vault_path / "02_Entities" / "Persons" / "Metternich.md")
        content = mett_note.read_text(encoding="utf-8")

        assert "[[Austria]]" in content
        assert "type: Person" in content
        assert "tags:" in content
        assert "aliases:" in content
        assert "## Summary" in content
        assert "## Relationships & Evidence" in content
        assert "## Source Documents" in content

    def test_frontmatter_format(self, tmp_output: Path) -> None:
        vault_dir = tmp_output / "vault3"
        config = ExportConfig(obsidian_vault_dir=str(vault_dir), output_dir=str(tmp_output))

        entity = Entity(
            name="Napoleon",
            entity_type=EntityType.PERSON,
            aliases=["Napoleon Bonaparte"],
            summary="Emperor of the French.",
            source_doc_ids=["src1"],
        )
        exporter = ObsidianExporter(config=config)
        vault_path = exporter.build_vault([entity], [])

        note = (vault_path / "02_Entities" / "Persons" / "Napoleon.md")
        content = note.read_text(encoding="utf-8")

        assert "type: Person" in content
        assert "Napoleon Bonaparte" in content
        assert "historical-entity" in content
        assert "person" in content


class TestFileStore:
    def test_save_and_load(self, tmp_output: Path) -> None:
        store = FileStore(tmp_output)
        entity = Entity(
            name="Test",
            entity_type=EntityType.PERSON,
            aliases=["T"],
            summary="Test entity.",
        )
        store.save_models("test_entities.json", [entity])
        loaded = store.load("test_entities.json")
        assert len(loaded) == 1
        assert loaded[0]["name"] == "Test"

    def test_empty_load(self, tmp_output: Path) -> None:
        store = FileStore(tmp_output)
        assert store.load("nonexistent.json") == []


class TestDemoCommand:
    def test_demo_runs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Demo command produces output at the expected location.

        The demo's use_semantic default would require a live embedder, so we
        force fuzzy resolution for the test.  Output paths are resolved
        against the app root by load_config, so we override them to land in
        tmp_path, matching the pattern in TestDemoRegression.
        """
        import artifice_graph.config as cfg_mod
        import artifice_graph.cli as cli_mod

        orig_load = cfg_mod.load_config

        def _load_config_override(*args: object, **kwargs: object) -> PipelineConfig:
            c = orig_load(*args, **kwargs)
            c.export.output_dir = str(tmp_path / "data" / "output")
            c.export.obsidian_vault_dir = str(tmp_path / "data" / "obsidian_vault")
            c.entity_resolution.use_semantic = False
            resolve_config_paths(c, tmp_path)
            return c

        monkeypatch.setattr(cfg_mod, "load_config", _load_config_override)
        monkeypatch.setattr(cli_mod, "load_config", _load_config_override)
        monkeypatch.chdir(tmp_path)

        from artifice_graph.cli import demo
        demo()
        output_dir = tmp_path / "data" / "output"
        assert (output_dir / "entities.json").exists()
        assert (output_dir / "relationships.json").exists()

        vault_dir = tmp_path / "data" / "obsidian_vault"
        assert (vault_dir / "01_Sources").exists()
        assert (vault_dir / "02_Entities" / "Persons").exists()


class MockBGEM3Embedder:
    """Deterministic mock embedder for testing semantic resolution.
    Produces vectors where similar strings get similar embeddings."""

    def __init__(self) -> None:
        self._dim = 16

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    def embed_single(self, text: str) -> list[float]:
        return self._hash_embed(text)

    def _hash_embed(self, text: str) -> list[float]:
        import hashlib, math
        normed = text.lower().strip()
        chars = [ord(c) for c in normed]
        vec = []
        for i in range(self._dim):
            seed = hashlib.md5(f"{i}:{normed}".encode()).digest()
            val = sum(chars[j % len(chars)] * seed[j % len(seed)] for j in range(min(len(chars), 16)))
            vec.append(float(val % 1000) / 1000.0)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


class TestSemanticResolver:
    def test_basic_merge(self) -> None:
        from artifice_graph.entity_resolution.semantic_resolver import SemanticEntityResolver
        from artifice_graph.config import EntityResolutionConfig

        embedder = MockBGEM3Embedder()
        config = EntityResolutionConfig(
            similarity_threshold=0.85,
            semantic_threshold=0.85,
            use_semantic=True,
        )
        resolver = SemanticEntityResolver(embedder=embedder, config=config)

        entities = [
            Entity(name="Klemens Metternich", entity_type=EntityType.PERSON, aliases=[], summary="Short"),
            Entity(
                name="Klemens von Metternich",
                entity_type=EntityType.PERSON,
                aliases=["Prince Metternich"],
                summary="Longer summary about the Austrian statesman.",
                source_doc_ids=["doc1"],
            ),
        ]
        relationships = [
            Relationship(source_entity="Klemens Metternich", target_entity="Austria", relationship_type="served")
        ]

        merged, updated = resolver.resolve(entities, relationships)
        assert len(merged) == 1
        assert merged[0].name == "Klemens von Metternich"
        assert "Klemens Metternich" in merged[0].aliases
        assert "Prince Metternich" in merged[0].aliases
        assert updated[0].source_entity == "Klemens von Metternich"

    def test_no_merge_different_entities(self) -> None:
        from artifice_graph.entity_resolution.semantic_resolver import SemanticEntityResolver
        from artifice_graph.config import EntityResolutionConfig

        embedder = MockBGEM3Embedder()
        config = EntityResolutionConfig(similarity_threshold=0.93, semantic_threshold=0.85)
        resolver = SemanticEntityResolver(embedder=embedder, config=config)

        entities = [
            Entity(name="Metternich", entity_type=EntityType.PERSON),
            Entity(name="Wellington", entity_type=EntityType.PERSON),
        ]
        merged, _ = resolver.resolve(entities, [])
        assert len(merged) == 2
