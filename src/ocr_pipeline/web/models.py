"""Pydantic request/response models for all web routes.

Consolidated here so every router file can import them without circular
references or duplicating model definitions across modules.
"""

from pydantic import BaseModel


class AddPathsRequest(BaseModel):
    paths: list[str]


class RemoveRequest(BaseModel):
    ids: list[str]


class StartRunRequest(BaseModel):
    stages: list[str]
    output_dir: str = "output"
    force: bool = False


class SkipRequest(BaseModel):
    id: str


class RawTextRequest(BaseModel):
    text: str


class TropyBrowseRequest(BaseModel):
    project: str
    list_id: int | None = None
    tag: str | None = None
    item_ids: list[int] | None = None


class TropyAddRequest(BaseModel):
    project: str
    item_ids: list[int] | None = None
    output_dir: str = "output"


class TropySendRequest(BaseModel):
    project: str
    item_ids: list[str] | None = None
    targets: list[str]
    stage: str = "cleaned"


class TropySendWriteRequest(TropySendRequest):
    make_backup: bool = True


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
