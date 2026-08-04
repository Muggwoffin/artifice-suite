# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""shared-ui — canonical design tokens and fonts for the Artifice Suite."""

from importlib import resources

__all__ = ["ASSETS"]

ASSETS = resources.files(__name__) / "assets"
