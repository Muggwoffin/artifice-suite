"""LLM edit result domain type — the schema target when draft is ported to the harness."""

from dataclasses import dataclass


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
