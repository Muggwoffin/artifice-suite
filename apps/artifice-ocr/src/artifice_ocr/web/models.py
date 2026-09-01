# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic request/response models for all web routes.

Consolidated here so every router file can import them without circular
references or duplicating model definitions across modules.
"""

from pydantic import BaseModel, Field, model_validator

from ..tropy_jsonld import MAX_FILE_BYTES


class AddPathsRequest(BaseModel):
    paths: list[str]


class RemoveRequest(BaseModel):
    ids: list[str]


class StartRunRequest(BaseModel):
    stages: list[str]
    output_dir: str = "output"
    project: str | None = None
    force: bool = False


class SkipRequest(BaseModel):
    id: str


class RawTextRequest(BaseModel):
    text: str


class TropyImportRequest(BaseModel):
    path: str | None = None
    content: str | None = Field(default=None, max_length=MAX_FILE_BYTES)
    filename: str | None = None  # display name; only meaningful with content

    @model_validator(mode="after")
    def _check_exactly_one_source(self) -> "TropyImportRequest":
        has_path = self.path is not None
        has_content = self.content is not None

        if has_path and has_content:
            raise ValueError("Provide either 'path' or 'content', not both")
        if not has_path and not has_content:
            raise ValueError("Provide either 'path' or 'content'")
        if self.filename is not None and not has_content:
            raise ValueError("'filename' is only valid with 'content'")
        return self


class TropyImportAddRequest(TropyImportRequest):
    groups: list[str] | None = None
    output_dir: str = "output"


class TropyExportRequest(BaseModel):
    item_ids: list[str] | None = None
    stage: str = "cleaned"
    path: str | None = None


class TropyExportHistoryRequest(BaseModel):
    item_ids: list[int]
    stage: str = "cleaned"
    path: str | None = None


class PdfExportRequest(BaseModel):
    folder: str
    stage: str = "cleaned"
    structure: bool = True
    output: str | None = None
    manifest: str | None = None
    format: str = "pdf"
    style: str = "readable"
    bilingual: bool = False


class ReorderRequest(BaseModel):
    drag_id: str
    drop_id: str
    before: bool = True


class ReprocessRequest(BaseModel):
    from_stage: str
    stages: list[str]


class BatchReplaceRequest(BaseModel):
    find: str
    replace: str
    stages: list[str]
    item_ids: list[str] | None = None


class TropyBrowseRequest(BaseModel):
    path: str


class TropyEnqueueRequest(BaseModel):
    path: str
    item_ids: list[int]
    output_dir: str = "output"
