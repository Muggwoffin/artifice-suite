# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

from artifice_graph.config import EntityResolutionConfig, load_config
from artifice_graph.models.entity import Entity, EntityType
from artifice_graph.models.relationship import Relationship

logger = logging.getLogger(__name__)


def _normalise(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalise(a), _normalise(b)).ratio()


class EntityResolver:
    """Deduplicate and merge entity nodes using name normalisation and fuzzy matching."""

    def __init__(self, config: EntityResolutionConfig | None = None) -> None:
        if config is None:
            config = load_config().entity_resolution
        self.config = config
        self.canonical_map: dict[str, str] = {}
        self.merged_entities: dict[str, Entity] = {}

    def resolve(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
    ) -> tuple[list[Entity], list[Relationship]]:
        merged = self._merge_entities(entities)
        rel_map = self._build_alias_map(merged)
        updated_rels = self._update_relationships(relationships, rel_map)
        return merged, updated_rels

    def _merge_entities(self, entities: list[Entity]) -> list[Entity]:
        clusters: dict[str, list[Entity]] = {}

        for entity in entities:
            norm = _normalise(entity.name)
            canonical_key: str | None = None
            for existing_key in clusters:
                if _similarity(norm, existing_key) >= self.config.similarity_threshold:
                    canonical_key = existing_key
                    break

            if canonical_key is None:
                canonical_key = norm
                clusters[canonical_key] = []

            clusters[canonical_key].append(entity)

        merged: list[Entity] = []
        for key, group in clusters.items():
            primary = self._pick_primary(group)
            all_aliases: list[str] = []
            all_source_ids: list[str] = []
            summaries: list[str] = []

            for ent in group:
                all_aliases.append(ent.name)
                all_source_ids.extend(ent.source_doc_ids)
                if ent.summary and ent.summary not in summaries:
                    summaries.append(ent.summary)
                for alias in ent.aliases:
                    if alias not in all_aliases:
                        all_aliases.append(alias)

            primary.name = group[0].name
            primary.aliases = [a for a in all_aliases if _normalise(a) != _normalise(primary.name)]
            primary.source_doc_ids = sorted(set(all_source_ids))
            primary.summary = " ".join(summaries[:3])

            self.merged_entities[primary.id] = primary
            merged.append(primary)
            for ent in group:
                self.canonical_map[_normalise(ent.name)] = primary.id
                self.canonical_map[_normalise(ent.name)] = primary.name
                for alias in ent.aliases:
                    self.canonical_map[_normalise(alias)] = primary.name

        return merged

    def _pick_primary(self, group: list[Entity]) -> Entity:
        scored = sorted(
            group,
            key=lambda e: (len(e.summary), len(e.aliases), len(e.source_doc_ids)),
            reverse=True,
        )
        return scored[0].model_copy(deep=True)

    def _build_alias_map(self, entities: list[Entity]) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for ent in entities:
            alias_map[_normalise(ent.name)] = ent.name
            for alias in ent.aliases:
                alias_map[_normalise(alias)] = ent.name
        return alias_map

    def _update_relationships(
        self,
        relationships: list[Relationship],
        alias_map: dict[str, str],
    ) -> list[Relationship]:
        updated: list[Relationship] = []
        for rel in relationships:
            src = alias_map.get(_normalise(rel.source_entity), rel.source_entity)
            tgt = alias_map.get(_normalise(rel.target_entity), rel.target_entity)
            updated.append(
                rel.model_copy(
                    update={"source_entity": src, "target_entity": tgt}
                )
            )
        return updated

    def get_canonical_name(self, name: str) -> str:
        return self.canonical_map.get(_normalise(name), name)

    def get_entity(self, name: str) -> Entity | None:
        canon = self.get_canonical_name(name)
        for eid, ent in self.merged_entities.items():
            if ent.name == canon:
                return ent
        return None
