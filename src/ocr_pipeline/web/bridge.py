"""Native dialogs exposed to the page when running inside a pywebview window.

Only imported by `server.main()` when pywebview is actually in use — the
server and the static frontend both work perfectly well without it (a browser
tab just falls back to typing a path), so nothing else in this package depends
on `webview` being installed.

Every method here is called from JavaScript as `pywebview.api.<name>(...)`,
which returns a Promise resolving to whatever the method returns.
"""

from typing import Any

FILE_TYPES = ("Documents (*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.pdf)",
             "All files (*.*)")


class Bridge:
    """The `js_api` object for the native window.

    Dialogs go through `webview.windows[0]` rather than a stored reference:
    the bridge instance is constructed before the window exists (it is passed
    *into* `create_window`), so there is nothing to point at yet at
    `__init__` time.
    """

    def _window(self):
        import webview
        return webview.windows[0]

    def browse_files(self) -> list[str]:
        import webview
        result = self._window().create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=True, file_types=FILE_TYPES,
        )
        return list(result) if result else []

    def browse_folder(self) -> str | None:
        import webview
        result = self._window().create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None

    def browse_output_dir(self) -> str | None:
        return self.browse_folder()

    def browse_tropy_project(self) -> str | None:
        """A .tropy bundle is a directory, so this is a folder picker too."""
        return self.browse_folder()

    def platform_info(self) -> dict[str, Any]:
        return {"native": True}
