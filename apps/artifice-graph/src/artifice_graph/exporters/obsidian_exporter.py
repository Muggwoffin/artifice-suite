# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

from artifice_graph.config import ExportConfig, load_config
from artifice_graph.entity_resolution.resolver import EntityResolver
from artifice_graph.models.document import Document, TextChunk
from artifice_graph.models.entity import Entity, EntityType
from artifice_graph.models.relationship import Relationship


class ObsidianExporter:
    """Build a hyperlinked Obsidian vault from extracted entities and relationships."""

    TYPE_FOLDER_MAP: dict[EntityType, str] = {
        EntityType.PERSON: "Persons",
        EntityType.ORGANIZATION: "Organizations",
        EntityType.LOCATION: "Locations",
        EntityType.EVENT: "Events",
        EntityType.CONCEPT: "Concepts",
    }

    def __init__(
        self,
        resolver: EntityResolver | None = None,
        config: ExportConfig | None = None,
    ) -> None:
        if config is None:
            config = load_config().export
        self.config = config
        self.resolver = resolver or EntityResolver()
        self.vault_root = Path(config.obsidian_vault_dir)

    def build_vault(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
        documents: list[Document] | None = None,
        chunks: list[TextChunk] | None = None,
    ) -> Path:
        self._create_folders()
        self._write_entity_notes(entities, relationships)
        self._write_source_notes(documents or [], chunks or [], entities)
        return self.vault_root

    def _create_folders(self) -> None:
        (self.vault_root / "01_Sources").mkdir(parents=True, exist_ok=True)
        for folder in self.TYPE_FOLDER_MAP.values():
            (self.vault_root / "02_Entities" / folder).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Entity notes
    # ------------------------------------------------------------------

    def _entity_filename(self, name: str) -> str:
        safe = name.replace("/", " - ").replace("\\", " - ")
        safe = re.sub(r'[<>:"|?*]', "", safe)
        return safe.strip()

    def _entity_folder(self, etype: EntityType) -> Path:
        folder = self.TYPE_FOLDER_MAP.get(etype, "Concepts")
        return self.vault_root / "02_Entities" / folder

    def _build_frontmatter(self, entity: Entity, relationships: list[Relationship]) -> str:
        related_names: list[str] = []
        for rel in relationships:
            if rel.source_entity == entity.name:
                related_names.append(rel.target_entity)
            elif rel.target_entity == entity.name:
                related_names.append(rel.source_entity)

        meta = {
            "type": entity.entity_type.value,
            "aliases": entity.aliases,
            "tags": [entity.entity_type.value.lower(), "historical-entity"],
            "related_entities": [f"[[{name}]]" for name in related_names],
        }
        return yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()

    def _entity_body(
        self, entity: Entity, relationships: list[Relationship], source_docs: list[str]
    ) -> str:
        parts: list[str] = []
        parts.append(self._build_frontmatter(entity, relationships))
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append(f"# {entity.canonical_name}")
        parts.append("")

        if entity.aliases:
            parts.append(f"**Also known as:** {', '.join(f'`{a}`' for a in entity.aliases)}")
            parts.append("")

        parts.append("## Summary")
        parts.append("")
        parts.append(entity.summary or "No summary available.")
        parts.append("")

        parts.append("## Relationships & Evidence")
        parts.append("")
        outgoing = [r for r in relationships if r.source_entity == entity.name]
        incoming = [r for r in relationships if r.target_entity == entity.name]

        if outgoing:
            parts.append("### Outgoing")
            parts.append("")
            for rel in outgoing:
                parts.append(f"- **{rel.relationship_type}** → [[{rel.target_entity}]]")
                if rel.time_frame:
                    parts.append(f"  - Time: {rel.time_frame}")
                if rel.evidence_quote:
                    parts.append(f"  - > \"{rel.evidence_quote}\"")
            parts.append("")

        if incoming:
            parts.append("### Incoming")
            parts.append("")
            for rel in incoming:
                parts.append(f"- **{rel.relationship_type}** ← [[{rel.source_entity}]]")
                if rel.time_frame:
                    parts.append(f"  - Time: {rel.time_frame}")
                if rel.evidence_quote:
                    parts.append(f"  - > \"{rel.evidence_quote}\"")
            parts.append("")

        if not outgoing and not incoming:
            parts.append("_No relationships extracted._")
            parts.append("")

        parts.append("## Source Documents")
        parts.append("")
        if source_docs:
            for doc_id in source_docs:
                parts.append(f"- [[01_Sources/{doc_id}]]")
        else:
            parts.append("_No source documents linked._")
        parts.append("")

        return "\n".join(parts)

    def _write_entity_notes(self, entities: list[Entity], relationships: list[Relationship]) -> None:
        entity_by_name: dict[str, Entity] = {e.name: e for e in entities}

        for entity in entities:
            folder = self._entity_folder(entity.entity_type)
            filename = self._entity_filename(entity.name) + ".md"
            filepath = folder / filename

            content = self._entity_body(entity, relationships, entity.source_doc_ids)
            filepath.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Source notes
    # ------------------------------------------------------------------

    def _build_entity_pattern(self, entities: list[Entity]) -> tuple[re.Pattern, dict[str, str]]:
        """Build a regex that matches any known entity name, longest-first."""
        names_sorted = sorted(
            [e.name for e in entities],
            key=len,
            reverse=True,
        )
        aliases_map: dict[str, str] = {}
        for e in entities:
            for alias in e.aliases:
                aliases_map[alias] = e.name

        all_names = list(names_sorted) + sorted(aliases_map.keys(), key=len, reverse=True)
        escaped = [re.escape(n) for n in all_names]
        pattern = re.compile(r"\b(" + "|".join(escaped) + r")\b")
        return pattern, aliases_map

    def _annotate_text(self, text: str, entities: list[Entity]) -> str:
        pattern, aliases_map = self._build_entity_pattern(entities)
        seen: set[str] = set()

        def _replace(match: re.Match) -> str:
            matched = match.group(0)
            canonical = aliases_map.get(matched, matched)
            key = f"{matched}:{canonical}"
            if key in seen:
                return matched
            seen.add(key)
            if matched == canonical:
                return f"[[{canonical}]]"
            return f"[[{canonical}|{matched}]]"

        return pattern.sub(_replace, text)

    def _source_note_content(self, doc: Document, chunks: list[TextChunk], entities: list[Entity]) -> str:
        parts: list[str] = []
        parts.append("---")
        parts.append("type: source-document")
        parts.append(f"filename: \"{doc.filename}\"")
        if doc.subfolder:
            parts.append(f"subfolder: \"{doc.subfolder}\"")
        parts.append("tags: [source, ocr-document]")
        parts.append("---")
        parts.append("")
        parts.append(f"# Source: {doc.filename}")
        parts.append("")
        doc_chunks = [c for c in chunks if c.document_id == doc.id]
        doc_chunks.sort(key=lambda c: c.chunk_index)

        for chunk in doc_chunks:
            annotated = self._annotate_text(chunk.text, entities)
            parts.append(f"## Chunk {chunk.chunk_index}")
            parts.append("")
            parts.append(annotated)
            parts.append("")
            parts.append("---")
            parts.append("")

        return "\n".join(parts)

    def _write_source_notes(
        self,
        documents: list[Document],
        chunks: list[TextChunk],
        entities: list[Entity],
    ) -> None:
        source_dir = self.vault_root / "01_Sources"
        for doc in documents:
            filename = self._entity_filename(doc.filename) + ".md"
            filepath = source_dir / filename
            content = self._source_note_content(doc, chunks, entities)
            filepath.write_text(content, encoding="utf-8")

        if not documents and chunks:
            for chunk in chunks:
                filepath = source_dir / f"{chunk.document_id}.md"
                if filepath.exists():
                    existing = filepath.read_text(encoding="utf-8")
                    annotated = self._annotate_text(chunk.text, entities)
                    with open(filepath, "a", encoding="utf-8") as f:
                        f.write(f"\n## Chunk {chunk.chunk_index}\n\n{annotated}\n")
                else:
                    annotated = self._annotate_text(chunk.text, entities)
                    frontmatter = (
                        "---\ntype: source-document\n"
                        f'filename: "{chunk.document_id}"\n'
                        "tags: [source, ocr-document]\n---\n\n"
                        f"# Source: {chunk.document_id}\n\n"
                        f"## Chunk {chunk.chunk_index}\n\n{annotated}\n"
                    )
                    filepath.write_text(frontmatter, encoding="utf-8")
