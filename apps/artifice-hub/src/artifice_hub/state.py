# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Persistent state for the Artifice Hub (platformdirs JSON file).

Stores the record of completed / failed installs, recently launched apps,
and user preferences so the dashboard is accurate across restarts.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path

import platformdirs


def _state_path() -> Path:
    """Return the path to the hub's JSON state file."""
    dir_ = Path(platformdirs.user_data_dir("artifice-hub", "ArtificeSuite"))
    dir_.mkdir(parents=True, exist_ok=True)
    return dir_ / "hub-state.json"


@dataclass
class HubState:
    """Persistent hub state stored as JSON."""

    installed: dict[str, str] = field(default_factory=dict)  # slug → version
    last_launched: dict[str, str] = field(default_factory=dict)  # slug → ISO timestamp
    # ── transient fields (not persisted) ──
    _path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls) -> HubState:
        path = _state_path()
        if not path.exists():
            return cls(_path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls(_path=path)
        return cls(
            installed=data.get("installed", {}),
            last_launched=data.get("last_launched", {}),
            _path=path,
        )

    def save(self) -> None:
        path = self._path or _state_path()
        with path.open("w", encoding="utf-8") as fh:
            json.dump(
                {"installed": self.installed, "last_launched": self.last_launched},
                fh,
                indent=2,
            )
        # Best-effort permissions clamp — touch the file with a read-only fd
        _fh = os.open(path, os.O_RDONLY)
        os.close(_fh)

    def record_install(self, slug: str, version: str) -> None:
        self.installed[slug] = version
        self.save()

    def record_uninstall(self, slug: str) -> None:
        self.installed.pop(slug, None)
        self.save()

    def record_launch(self, slug: str) -> None:
        from datetime import datetime

        self.last_launched[slug] = datetime.now(UTC).isoformat()
        self.save()
