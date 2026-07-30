# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    EVENT = "Event"
    CONCEPT = "Concept"


class Entity(BaseModel):
    """A canonical entity extracted from source text."""

    id: str = ""
    name: str
    entity_type: EntityType
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    source_doc_ids: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None

    def model_post_init(self, __context: object) -> None:
        if not self.id:
            self.id = self._make_id(self.name)

    @staticmethod
    def _make_id(name: str) -> str:
        normalised = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        normalised = normalised.lower().strip()
        normalised = re.sub(r"[^a-z0-9]+", "_", normalised)
        return normalised.strip("_")

    @property
    def canonical_name(self) -> str:
        return self.name
