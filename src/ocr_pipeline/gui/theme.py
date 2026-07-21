"""Central palette and ttk style setup.

The old GUI hard-coded colours at every call site. Everything visual now
comes from here, so restyling is a one-file change and the ttk widgets
(Notebook, Treeview, Combobox) stop rendering in default grey.
"""

from tkinter import ttk

# Catppuccin Mocha, matching the original palette.
BG = "#1e1e2e"
FG = "#cdd6f4"
FG_DIM = "#9399b2"
ACCENT = "#89b4fa"
ACCENT_DIM = "#45475a"
SUCCESS = "#a6e3a1"
WARNING = "#f9e2af"
ERROR = "#f38ba8"
MAUVE = "#cba6f7"
TEAL = "#94e2d5"
ENTRY_BG = "#313244"
FRAME_BG = "#181825"
LIST_BG = "#11111b"
SEL_BG = "#585b70"

# Diff highlighting in the comparison viewer.
DIFF_INSERT = "#2a3b2a"
DIFF_DELETE = "#3b2a2f"
DIFF_REPLACE = "#3b3524"

FONT = ("Consolas", 10)
FONT_BOLD = ("Consolas", 10, "bold")
FONT_SMALL = ("Consolas", 9)
FONT_TITLE = ("Segoe UI", 14, "bold")
FONT_HEAD = ("Segoe UI", 11, "bold")

# Per-state colours for queue rows and stage cells.
STATE_COLORS = {
    "pending": FG_DIM,
    "running": ACCENT,
    "done": SUCCESS,
    "skipped": WARNING,
    "failed": ERROR,
    "cancelled": FG_DIM,
}

STATE_GLYPHS = {
    "pending": "·",
    "running": "▶",
    "done": "✓",
    "skipped": "⤼",
    "failed": "✗",
    "cancelled": "—",
}


def apply(root) -> ttk.Style:
    """Install the dark ttk theme on the given root window."""
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BG, foreground=FG, font=FONT)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=FRAME_BG)
    style.configure("TLabel", background=BG, foreground=FG, font=FONT)
    style.configure("Card.TLabel", background=FRAME_BG, foreground=FG)
    style.configure("Title.TLabel", background=BG, foreground=ACCENT, font=FONT_TITLE)
    style.configure("Head.TLabel", background=BG, foreground=FG, font=FONT_HEAD)
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM, font=FONT_SMALL)

    # Notebook -------------------------------------------------------------
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(8, 6, 8, 0))
    style.configure(
        "TNotebook.Tab",
        background=FRAME_BG, foreground=FG_DIM,
        padding=(18, 8), font=FONT_BOLD, borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", BG), ("active", ACCENT_DIM)],
        foreground=[("selected", ACCENT), ("active", FG)],
    )

    # Buttons --------------------------------------------------------------
    style.configure(
        "TButton",
        background=ACCENT_DIM, foreground=FG,
        borderwidth=0, focusthickness=0, padding=(10, 5), font=FONT,
    )
    style.map(
        "TButton",
        background=[("active", SEL_BG), ("disabled", FRAME_BG)],
        foreground=[("disabled", FG_DIM)],
    )
    style.configure("Accent.TButton", background=ACCENT, foreground=BG, font=FONT_BOLD)
    style.map(
        "Accent.TButton",
        background=[("active", TEAL), ("disabled", ACCENT_DIM)],
        foreground=[("disabled", FG_DIM)],
    )
    style.configure("Danger.TButton", background=ACCENT_DIM, foreground=ERROR)
    style.map("Danger.TButton", background=[("active", ERROR)],
              foreground=[("active", BG)])

    # Inputs ---------------------------------------------------------------
    style.configure(
        "TEntry",
        fieldbackground=ENTRY_BG, foreground=FG, insertcolor=FG,
        borderwidth=0, padding=4,
    )
    style.configure(
        "TCombobox",
        fieldbackground=ENTRY_BG, background=ACCENT_DIM, foreground=FG,
        arrowcolor=FG, borderwidth=0, padding=4,
    )
    style.map("TCombobox", fieldbackground=[("readonly", ENTRY_BG)])
    style.configure(
        "TCheckbutton",
        background=BG, foreground=FG, focuscolor=BG,
        indicatorcolor=ENTRY_BG, font=FONT,
    )
    style.map("TCheckbutton",
              background=[("active", BG)],
              indicatorcolor=[("selected", ACCENT)])
    style.configure("Card.TCheckbutton", background=FRAME_BG)
    style.map("Card.TCheckbutton", background=[("active", FRAME_BG)])

    # Treeview -------------------------------------------------------------
    style.configure(
        "Treeview",
        background=LIST_BG, fieldbackground=LIST_BG, foreground=FG,
        borderwidth=0, rowheight=24, font=FONT,
    )
    style.configure(
        "Treeview.Heading",
        background=ACCENT_DIM, foreground=FG,
        font=FONT_BOLD, borderwidth=0, padding=(6, 5),
    )
    style.map("Treeview.Heading", background=[("active", SEL_BG)])
    style.map("Treeview",
              background=[("selected", SEL_BG)],
              foreground=[("selected", FG)])

    # Misc -----------------------------------------------------------------
    style.configure(
        "TProgressbar",
        background=ACCENT, troughcolor=FRAME_BG,
        borderwidth=0, thickness=6,
    )
    style.configure("TPanedwindow", background=BG)
    style.configure("TSeparator", background=ACCENT_DIM)
    style.configure(
        "Vertical.TScrollbar",
        background=ACCENT_DIM, troughcolor=FRAME_BG,
        borderwidth=0, arrowcolor=FG,
    )
    style.map("Vertical.TScrollbar", background=[("active", SEL_BG)])

    return style
