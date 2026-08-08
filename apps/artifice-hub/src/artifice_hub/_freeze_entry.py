# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entry point for the frozen artifice-hub executable.

Imports server.main() through the normal Python import system so that
relative imports inside server.py resolve correctly.  Running server.py
as a bare script loses the package context.
"""

from artifice_hub.web.server import main

if __name__ == "__main__":
    main()
