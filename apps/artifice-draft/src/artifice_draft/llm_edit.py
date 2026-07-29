"""LLM edit result types — domain and wire schema.

``LLMEdit`` is the domain object; ``_DraftEditEntry`` / ``_DraftEditsShape``
are the wire schema passed to :func:`model_harness.driver.run_structured`.
"""

from dataclasses import dataclass

from pydantic import BaseModel


# -- Domain type ----------------------------------------------------------------

@dataclass
class LLMEdit:
    """A single edit result from the model."""

    paragraph_index: int = 0
    original_text: str = ""
    edited_text: str | None = None  # None means "no change"
    status: str = "unchanged"  # or "edited", "error"

    def is_changed(self) -> bool:
        return self.edited_text is not None and self.edited_text != self.original_text

    @staticmethod
    def to_edits_dict(edits: list["LLMEdit"]) -> dict[int, str | None]:
        """Convert a list of LLMEdit objects to a dict mapping index → edited text."""
        return {e.paragraph_index: e.edited_text for e in edits}


# -- Wire schema (model output shape) ------------------------------------------

class _DraftEditEntry(BaseModel):
    """A single edit entry in the model's JSON response.

    Every field is optional with a reasonable default so the schema can survive
    a model that omits a key — ``_map_response_to_batch_edits`` handles the
    business-logic defaults at the mapping layer.
    """

    paragraph_index: int | None = None
    edited_text: str | None = None
    status: str = "unchanged"


class _DraftEditsShape(BaseModel):
    """Schema for the harness structured-extraction call.

    This is the JSON Schema passed to :func:`~model_harness.driver.run_structured`
    and injected into the prompt.  The model is expected to return a JSON object
    with an ``edits`` array, each entry carrying ``paragraph_index``,
    ``edited_text`` and ``status``.
    """

    edits: list[_DraftEditEntry]
