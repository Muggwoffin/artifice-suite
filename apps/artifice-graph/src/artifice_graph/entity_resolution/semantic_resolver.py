# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import yaml

from artifice_graph.config import EmbeddingConfig, EntityResolutionConfig, load_config
from artifice_graph.embedding.bge_embedder import BGEM3Embedder
from artifice_graph.models.entity import Entity, EntityType
from artifice_graph.models.relationship import Relationship

logger = logging.getLogger(__name__)


def _normalise(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _fuzzy_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    return SequenceMatcher(None, _normalise(a), _normalise(b)).ratio() >= threshold


def _load_aliases(aliases_file: str) -> dict[str, str]:
    """Load manual alias overrides from a YAML file.

    Format:
      aliases:
        "Canonical Name": ["alias1", "alias2"]
    """
    path = Path(aliases_file)
    if not path.exists():
        logger.debug("No aliases file found at %s", aliases_file)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("aliases", {})
    result: dict[str, str] = {}
    for canonical, alias_list in raw.items():
        if isinstance(alias_list, str):
            alias_list = [alias_list]
        for alias in alias_list:
            result[_normalise(alias)] = canonical
    if result:
        logger.info("Loaded %d manual alias overrides from %s", len(result), aliases_file)
    return result


class SemanticEntityResolver:
    """Embedding-based entity deduplication using bge-m3 via Ollama.

    Strategy:
      1. Apply manual alias overrides from YAML
      2. Build candidate pairs via fast fuzzy pre-filter
      3. Embed each unique entity name with bge-m3
      4. Merge pairs where cosine_similarity >= semantic_threshold
      5. Cluster via greedy union-find
    """

    def __init__(
        self,
        embedder: BGEM3Embedder | None = None,
        config: EntityResolutionConfig | None = None,
    ) -> None:
        if config is None:
            config = load_config().entity_resolution
        self.config = config
        self.embedder = embedder or BGEM3Embedder(
            EmbeddingConfig(model=config.embedding_model)
        )
        self.canonical_map: dict[str, str] = {}
        self.merged_entities: dict[str, Entity] = {}
        self.manual_aliases: dict[str, str] = _load_aliases(config.aliases_file)

    # ── public API ──────────────────────────────────────────────────────

    def resolve(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
    ) -> tuple[list[Entity], list[Relationship]]:
        if not entities:
            return [], []

        if self.manual_aliases:
            entities = self._apply_manual_aliases(entities)

        merged = self._merge_entities(entities)
        alias_map = self._build_alias_map(merged)
        updated_rels = self._update_relationships(relationships, alias_map)
        return merged, updated_rels

    # ── manual alias application ─────────────────────────────────────────

    def _apply_manual_aliases(self, entities: list[Entity]) -> list[Entity]:
        updated: list[Entity] = []
        for ent in entities:
            norm = _normalise(ent.name)
            canonical = self.manual_aliases.get(norm)
            if canonical and canonical != ent.name:
                ent.aliases.append(ent.name)
                ent.name = canonical
                ent.id = Entity._make_id(canonical)
            for alias_to_add in self.manual_aliases.get(norm, []):
                if alias_to_add not in ent.aliases and alias_to_add != ent.name:
                    ent.aliases.append(alias_to_add)
            updated.append(ent)
        return updated

    # ── core merging ────────────────────────────────────────────────────

    def _merge_entities(self, entities: list[Entity]) -> list[Entity]:
        names = list({e.name for e in entities})
        entity_by_name: dict[str, list[Entity]] = {}
        for ent in entities:
            entity_by_name.setdefault(ent.name, []).append(ent)

        logger.info("Semantic dedup: %d unique names, embedding…", len(names))
        try:
            from rich.progress import Progress, SpinnerColumn, TextColumn
            with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
                task = progress.add_task(f"Embedding {len(names)} entity names…", total=None)
                embeddings = self.embedder.embed(names)
                progress.update(task, description=f"Embedded {len(names)} names")
        except ImportError:
            embeddings = self.embedder.embed(names)

        name_emb: dict[str, list[float]] = dict(zip(names, embeddings))

        logger.info("Computing pairwise similarity…")
        candidates = self._find_candidate_pairs(names, name_emb)
        logger.info("Found %d candidate merge pairs", len(candidates))

        parent = {n: n for n in names}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for a, b in candidates:
            union(a, b)

        clusters: dict[str, list[str]] = {}
        for n in names:
            root = find(n)
            clusters.setdefault(root, []).append(n)

        merged: list[Entity] = []
        for _root, cluster_names in clusters.items():
            group: list[Entity] = []
            for cname in cluster_names:
                group.extend(entity_by_name[cname])

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

            primary.aliases = [
                a for a in all_aliases if _normalise(a) != _normalise(primary.name)
            ]
            primary.source_doc_ids = sorted(set(all_source_ids))
            primary.summary = " ".join(summaries[:3])

            self.merged_entities[primary.id] = primary
            merged.append(primary)
            for ent in group:
                self.canonical_map[_normalise(ent.name)] = primary.name
                for alias in ent.aliases:
                    self.canonical_map[_normalise(alias)] = primary.name

        logger.info("Merged %d entities → %d canonical", len(entities), len(merged))
        return merged

    # ── candidate pair detection ─────────────────────────────────────────

    def _find_candidate_pairs(
        self,
        names: list[str],
        name_emb: dict[str, list[float]],
    ) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        n = len(names)

        exact_similar = set()
        for i in range(n):
            for j in range(i + 1, n):
                a, b = names[i], names[j]
                if _normalise(a) == _normalise(b):
                    exact_similar.add((a, b))
                    continue
                if _fuzzy_similar(a, b, self.config.similarity_threshold):
                    exact_similar.add((a, b))

        emb_pairs = set()
        if n <= 500:
            try:
                from rich.progress import Progress, TextColumn
                with Progress(TextColumn("{task.description}"), transient=True) as progress:
                    task = progress.add_task(
                        f"Computing pairwise similarity for {n} names…", total=n * (n - 1) // 2
                    )
                    count = 0
                    for i in range(n):
                        for j in range(i + 1, n):
                            a, b = names[i], names[j]
                            sim = BGEM3Embedder.cosine_similarity(
                                name_emb[a], name_emb[b]
                            )
                            if sim >= self.config.semantic_threshold:
                                emb_pairs.add((a, b))
                            count += 1
                        progress.update(task, completed=count)
            except ImportError:
                for i in range(n):
                    for j in range(i + 1, n):
                        a, b = names[i], names[j]
                        sim = BGEM3Embedder.cosine_similarity(name_emb[a], name_emb[b])
                        if sim >= self.config.semantic_threshold:
                            emb_pairs.add((a, b))

        return list(exact_similar | emb_pairs)

    # ── helpers ──────────────────────────────────────────────────────────

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
                rel.model_copy(update={"source_entity": src, "target_entity": tgt})
            )
        return updated

    def get_canonical_name(self, name: str) -> str:
        return self.canonical_map.get(_normalise(name), name)

    def get_entity(self, name: str) -> Entity | None:
        canon = self.get_canonical_name(name)
        for _eid, ent in self.merged_entities.items():
            if ent.name == canon:
                return ent
        return None
