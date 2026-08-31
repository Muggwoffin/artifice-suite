# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from artifice_graph.config import ExportConfig, load_config
from artifice_graph.models.entity import Entity
from artifice_graph.models.relationship import Relationship
from artifice_graph.storage.graph_store import GraphStore
from artifice_output import ProjectLayout


_FORMAT_EXTENSIONS: dict[str, str] = {
    "graphml": ".graphml",
    "gexf": ".gexf",
    "json": ".json",
    "csv": ".csv",
    "cypher": ".cypher",
}


class GraphExporter:
    """Build a NetworkX graph and export to multiple formats."""

    def __init__(self, config: ExportConfig | None = None) -> None:
        if config is None:
            config = load_config().export
        self.config = config
        self.store = GraphStore()

    def build_graph(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
    ) -> None:
        entity_ids: dict[str, str] = {}
        for ent in entities:
            self.store.add_entity(ent)
            entity_ids[ent.name] = ent.id
            for alias in ent.aliases:
                entity_ids[alias] = ent.id

        for rel in relationships:
            src_id = entity_ids.get(rel.source_entity)
            tgt_id = entity_ids.get(rel.target_entity)
            if src_id and tgt_id:
                self.store.add_relationship(rel, src_id, tgt_id)

    def export(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
        formats: list[str] | None = None,
    ) -> dict[str, Path]:
        self.build_graph(entities, relationships)
        root = Path(self.config.output_dir)
        output = (
            ProjectLayout(root.parent.parent, root.name, create=True).export_dir("graph")
            if (root / "project.json").is_file()
            else root
        )
        output.mkdir(parents=True, exist_ok=True)

        if formats is None:
            formats = list(self.config.graph_formats)

        results: dict[str, Path] = {}
        for fmt in formats:
            fmt = fmt.lower()
            ext = _FORMAT_EXTENSIONS.get(fmt, f".{fmt}")
            base = output / f"knowledge_graph{ext}"
            if fmt == "graphml":
                results["graphml"] = self.store.export_graphml(base)
            elif fmt == "gexf":
                results["gexf"] = self.store.export_gexf(base)
            elif fmt == "json":
                results["json"] = self.store.export_json(base)
            elif fmt == "csv":
                csv_results = self.store.export_csv(base)
                results.update(csv_results)
            elif fmt == "cypher":
                results["cypher"] = self.store.export_cypher(base)
            else:
                from rich.console import Console
                Console().print(f"[yellow]Unknown format '{fmt}', skipping.[/yellow]")

        return results

    def summary(self) -> str:
        return (
            f"Graph: {self.store.node_count} nodes, "
            f"{self.store.edge_count} edges"
        )
