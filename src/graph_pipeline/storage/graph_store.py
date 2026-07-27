from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import networkx as nx

from graph_pipeline.models.entity import Entity, EntityType
from graph_pipeline.models.relationship import Relationship

_ENTITY_COLORS: dict[str, tuple[int, int, int]] = {
    EntityType.PERSON.value: (137, 180, 250),
    EntityType.ORGANIZATION.value: (166, 227, 161),
    EntityType.LOCATION.value: (249, 226, 175),
    EntityType.EVENT.value: (245, 194, 231),
    EntityType.CONCEPT.value: (148, 226, 213),
}


def _entity_color(entity_type: str) -> tuple[int, int, int]:
    return _ENTITY_COLORS.get(entity_type, (180, 180, 180))


def _degree_size(degree: int, min_s: float = 20, max_s: float = 80) -> float:
    if degree <= 0:
        return min_s
    return min(max_s, min_s + degree * 8)


class GraphStore:
    """NetworkX-backed graph with export to GraphML, GEXF, JSON, CSV."""

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self._has_viz = False

    def add_entity(self, entity: Entity) -> None:
        self.graph.add_node(
            entity.id,
            label=entity.canonical_name,
            entity_type=entity.entity_type.value,
            aliases="|".join(entity.aliases),
            summary=entity.summary,
        )

    def add_relationship(self, rel: Relationship, source_id: str, target_id: str) -> None:
        self.graph.add_edge(
            source_id,
            target_id,
            relationship_type=rel.relationship_type,
            time_frame=rel.time_frame,
            evidence_quote=rel.evidence_quote,
            confidence=rel.confidence_score,
        )

    def _add_viz_attributes(self) -> None:
        if self._has_viz:
            return
        for node_id, attrs in self.graph.nodes(data=True):
            etype = attrs.get("entity_type", "Person")
            r, g, b = _entity_color(etype)
            deg = self.graph.degree(node_id)
            attrs["r"] = r
            attrs["g"] = g
            attrs["b"] = b
            attrs["viz_size"] = _degree_size(deg)
        self._has_viz = True

    def _degree_map(self) -> dict[str, int]:
        return dict(self.graph.degree())

    def export_graphml(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._add_viz_attributes()
        nx.write_graphml(self.graph, str(path))
        return path

    def export_gexf(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._add_viz_attributes()
        for nid, attrs in self.graph.nodes(data=True):
            attrs["viz"] = {
                "color": {
                    "r": attrs.get("r", 180),
                    "g": attrs.get("g", 180),
                    "b": attrs.get("b", 180),
                    "a": 1.0,
                },
                "size": attrs.get("viz_size", 30),
            }
        nx.write_gexf(self.graph, str(path), version="1.2draft")
        for nid, _ in self.graph.nodes(data=True):
            self.graph.nodes[nid].pop("viz", None)
        return path

    def export_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._add_viz_attributes()
        data = nx.node_link_data(self.graph)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return path

    def export_csv(self, path: str | Path) -> dict[str, Path]:
        base = Path(path)
        base.parent.mkdir(parents=True, exist_ok=True)
        nodes_path = base.with_name(base.stem + "_nodes.csv")
        edges_path = base.with_name(base.stem + "_edges.csv")

        with open(nodes_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "label", "entity_type", "aliases", "summary", "degree"])
            deg_map = self._degree_map()
            for nid, attrs in self.graph.nodes(data=True):
                writer.writerow([
                    nid,
                    attrs.get("label", ""),
                    attrs.get("entity_type", ""),
                    attrs.get("aliases", ""),
                    attrs.get("summary", ""),
                    deg_map.get(nid, 0),
                ])

        with open(edges_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["source", "target", "relationship_type", "time_frame", "evidence", "confidence"])
            for src, tgt, attrs in self.graph.edges(data=True):
                writer.writerow([
                    src,
                    tgt,
                    attrs.get("relationship_type", ""),
                    attrs.get("time_frame", ""),
                    attrs.get("evidence_quote", ""),
                    attrs.get("confidence", ""),
                ])

        return {"nodes_csv": nodes_path, "edges_csv": edges_path}

    def export_cypher(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for node_id, attrs in self.graph.nodes(data=True):
            label = attrs.get("entity_type", "Entity")
            safe_label = label.replace(" ", "")
            props = ", ".join(
                f'{k}: "{_escape(v)}"' for k, v in attrs.items() if v and k != "viz"
            )
            lines.append(f'CREATE (n:{safe_label} {{id: "{_escape(node_id)}", {props}}});')
        for src, tgt, attrs in self.graph.edges(data=True):
            rel_type = attrs.get("relationship_type", "RELATED_TO").upper().replace(" ", "_")
            props = ", ".join(
                f'{k}: "{_escape(v)}"' for k, v in attrs.items() if v
            )
            src_esc = _escape(src)
            tgt_esc = _escape(tgt)
            match_clause = f'MATCH (a {{id: "{src_esc}"}}), (b {{id: "{tgt_esc}"}}) '
            create_clause = f'CREATE (a)-[:{rel_type} {{{props}}}]->(b);'
            lines.append(match_clause + create_clause)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()


def _escape(s: str) -> str:
    return str(s).replace('"', '\\"').replace("\n", " ")
