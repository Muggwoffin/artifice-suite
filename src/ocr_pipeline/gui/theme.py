"""Palette, typography and ttk styles.

Derived from the design tokens in the public_history site stylesheet
(https://github.com/Muggwoffin/public_history — `style.css` `:root`), so the
desktop tool reads as part of the same body of work as the website: a
"paper and ink" editorial look rather than a terminal.

Two palettes are provided, matching the site's light default and its
`prefers-color-scheme: dark` block. The palette is chosen once at startup
(config key `gui_theme`: "paper" or "night") because tk widgets take their
colours at construction time.

Font families follow the site's declared fallback chains. Playfair Display,
Libre Baskerville and Archivo are webfonts and usually absent locally, so the
chain resolves to Georgia / Franklin Gothic Medium — which is exactly what the
site falls back to. Install the three Google Fonts and this picks them up with
no code change.
"""

from tkinter import ttk

# --------------------------------------------------------------------------- #
# palettes — values quoted from style.css :root
# --------------------------------------------------------------------------- #

PAPER = {
    "paper": "#f6f3ea",
    "paper_raised": "#fbf9f3",
    "paper_recessed": "#efebdf",
    "ink": "#1b1813",
    "ink_soft": "#4b463d",
    "ink_faint": "#716c5e",
    "rule": "#ddd6c6",
    "rule_strong": "#c6bda9",
    "accent": "#2f7d45",
    "accent_deep": "#1f5a31",
    "accent_wash": "#e8ebde",       # --accent-wash flattened onto --paper
    "gold": "#bf9b30",
    # The guide defines no error colour; this oxblood is chosen to sit with
    # the gold and green rather than shout over them.
    "error": "#9a3324",
    "indigo": "#3d5a80",
    "on_accent": "#f6f3ea",
    "diff_insert": "#dcead9",
    "diff_delete": "#f2ddd9",
    "diff_replace": "#f6ead1",
    "marker": "#efe0b4",
}

NIGHT = {
    "paper": "#161310",
    "paper_raised": "#1f1b16",
    "paper_recessed": "#100e0b",
    "ink": "#e8e2d3",
    "ink_soft": "#beb5a3",
    "ink_faint": "#948c7c",
    "rule": "#38332b",
    "rule_strong": "#5b554a",
    "accent": "#4aa066",
    "accent_deep": "#7cc492",
    "accent_wash": "#1e2a20",
    "gold": "#d4b155",
    "error": "#c76354",
    "indigo": "#7d95bd",
    "on_accent": "#10120f",
    "diff_insert": "#1e2b1f",
    "diff_delete": "#2f1f1c",
    "diff_replace": "#2e2718",
    "marker": "#3a3120",
}

PALETTES = {"paper": PAPER, "night": NIGHT}

# --------------------------------------------------------------------------- #
# active values — rebound by use(); every widget reads these as theme.NAME
# --------------------------------------------------------------------------- #

BG = FG = FG_DIM = FG_SOFT = ""
ACCENT = ACCENT_DEEP = ACCENT_DIM = ""
SUCCESS = WARNING = ERROR = GOLD = INDIGO = ""
ENTRY_BG = FRAME_BG = LIST_BG = SEL_BG = RULE = ON_ACCENT = ""
DIFF_INSERT = DIFF_DELETE = DIFF_REPLACE = MARKER_BG = ""

_ACTIVE = "paper"

# Font family chains, exactly as declared in style.css.
_DISPLAY_CHAIN = ("Playfair Display", "Georgia", "Times New Roman")
_BODY_CHAIN = ("Libre Baskerville", "Georgia", "Times New Roman")
_SANS_CHAIN = ("Archivo", "Franklin Gothic Medium", "Arial Narrow", "Segoe UI")
_MONO_CHAIN = ("Cascadia Mono", "Consolas", "Courier New")

# Sensible defaults so importing this module never fails before apply().
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_LABEL = ("Segoe UI", 8, "bold")
FONT_TITLE = ("Georgia", 19, "bold")
FONT_HEAD = ("Georgia", 12, "bold")
FONT_BODY = ("Georgia", 11)
FONT_MONO = ("Consolas", 10)
FONT_STAT = ("Georgia", 22, "bold")

STATE_COLORS: dict[str, str] = {}

# Glyphs kept plain — the paper look does not want dingbats.
STATE_GLYPHS = {
    "pending": "·",
    "running": "▸",
    "done": "✓",
    "skipped": "–",
    "failed": "✕",
    "cancelled": "—",
}


def use(name: str) -> None:
    """Bind the active palette. Call before building any widgets."""
    global BG, FG, FG_DIM, FG_SOFT, ACCENT, ACCENT_DEEP, ACCENT_DIM
    global SUCCESS, WARNING, ERROR, GOLD, INDIGO
    global ENTRY_BG, FRAME_BG, LIST_BG, SEL_BG, RULE, ON_ACCENT
    global DIFF_INSERT, DIFF_DELETE, DIFF_REPLACE, MARKER_BG
    global STATE_COLORS, _ACTIVE

    p = PALETTES.get(name, PAPER)
    _ACTIVE = name if name in PALETTES else "paper"

    BG = p["paper"]
    FRAME_BG = p["paper_raised"]
    LIST_BG = p["paper_raised"]
    ENTRY_BG = p["paper_recessed"]
    FG = p["ink"]
    FG_SOFT = p["ink_soft"]
    FG_DIM = p["ink_faint"]
    RULE = p["rule"]
    ACCENT_DIM = p["rule"]
    SEL_BG = p["accent_wash"]
    ACCENT = p["accent"]
    ACCENT_DEEP = p["accent_deep"]
    ON_ACCENT = p["on_accent"]
    GOLD = p["gold"]
    INDIGO = p["indigo"]
    SUCCESS = p["accent"]
    WARNING = p["gold"]
    ERROR = p["error"]
    DIFF_INSERT = p["diff_insert"]
    DIFF_DELETE = p["diff_delete"]
    DIFF_REPLACE = p["diff_replace"]
    MARKER_BG = p["marker"]

    STATE_COLORS = {
        "pending": FG_DIM,
        "running": ACCENT,
        "done": FG,
        "skipped": FG_DIM,
        "failed": ERROR,
        "cancelled": FG_DIM,
    }


use("paper")


# Chart series, in the order Analytics draws them.
def chart_colors() -> list[str]:
    return [ACCENT, GOLD, INDIGO]


def _resolve_fonts(root) -> None:
    """Pick the first installed family from each of the site's font chains."""
    global FONT, FONT_BOLD, FONT_SMALL, FONT_LABEL, FONT_TITLE
    global FONT_HEAD, FONT_BODY, FONT_MONO, FONT_STAT

    import tkinter.font as tkfont

    available = set(tkfont.families(root))

    def pick(chain):
        return next((f for f in chain if f in available), chain[-1])

    display = pick(_DISPLAY_CHAIN)
    body = pick(_BODY_CHAIN)
    sans = pick(_SANS_CHAIN)
    mono = pick(_MONO_CHAIN)

    # Sans carries the UI chrome (nav, buttons, table headings); serif carries
    # titles and document text — the same division the site uses.
    FONT = (sans, 10)
    FONT_BOLD = (sans, 10, "bold")
    FONT_SMALL = (sans, 9)
    FONT_LABEL = (sans, 8, "bold")
    FONT_TITLE = (display, 19, "bold")
    FONT_HEAD = (display, 12, "bold")
    FONT_BODY = (body, 11)
    FONT_MONO = (mono, 10)
    FONT_STAT = (display, 22, "bold")


def apply(root, name: str | None = None) -> ttk.Style:
    """Install the palette, resolve fonts, and configure ttk styles."""
    if name:
        use(name)
    _resolve_fonts(root)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BG, foreground=FG, font=FONT)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=FRAME_BG)
    style.configure("Rule.TFrame", background=RULE)
    style.configure("TLabel", background=BG, foreground=FG, font=FONT)
    style.configure("Card.TLabel", background=FRAME_BG, foreground=FG)
    style.configure("Title.TLabel", background=BG, foreground=FG, font=FONT_TITLE)
    style.configure("Head.TLabel", background=BG, foreground=FG, font=FONT_HEAD)
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM, font=FONT_SMALL)
    style.configure("Label.TLabel", background=BG, foreground=FG_DIM, font=FONT_LABEL)

    # Notebook — flat nav, no tab boxes. clam draws a 3D border on tabs via
    # bordercolor/lightcolor/darkcolor, so those are flattened to the page
    # colour and selection is carried by weight and colour alone.
    style.configure("TNotebook", background=BG, borderwidth=0,
                    bordercolor=BG, lightcolor=BG, darkcolor=BG,
                    tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=FG_DIM,
                    padding=(18, 10), font=FONT_BOLD, borderwidth=0,
                    bordercolor=BG, lightcolor=BG, darkcolor=BG,
                    focuscolor=BG)
    style.map(
        "TNotebook.Tab",
        background=[("selected", BG), ("active", BG)],
        foreground=[("selected", ACCENT), ("active", FG)],
        bordercolor=[("selected", BG), ("active", BG)],
        lightcolor=[("selected", BG), ("active", BG)],
        darkcolor=[("selected", BG), ("active", BG)],
        expand=[("selected", (0, 0, 0, 0))],
    )

    # Buttons
    style.configure("TButton", background=FRAME_BG, foreground=FG,
                    bordercolor=RULE, borderwidth=1, focusthickness=0,
                    padding=(12, 6), font=FONT, relief="flat")
    style.map(
        "TButton",
        background=[("active", SEL_BG), ("disabled", BG)],
        foreground=[("disabled", FG_DIM)],
        bordercolor=[("active", ACCENT)],
    )
    style.configure("Accent.TButton", background=ACCENT, foreground=ON_ACCENT,
                    bordercolor=ACCENT, font=FONT_BOLD)
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_DEEP), ("disabled", RULE)],
        foreground=[("disabled", FG_DIM)],
        bordercolor=[("active", ACCENT_DEEP), ("disabled", RULE)],
    )
    style.configure("Danger.TButton", background=FRAME_BG, foreground=ERROR,
                    bordercolor=RULE)
    style.map("Danger.TButton",
              background=[("active", ERROR)],
              foreground=[("active", ON_ACCENT)],
              bordercolor=[("active", ERROR)])

    # Inputs
    style.configure("TEntry", fieldbackground=ENTRY_BG, foreground=FG,
                    insertcolor=FG, bordercolor=RULE, borderwidth=1,
                    lightcolor=RULE, darkcolor=RULE, padding=6)
    style.map("TEntry", bordercolor=[("focus", ACCENT)])
    style.configure("TCombobox", fieldbackground=ENTRY_BG, background=FRAME_BG,
                    foreground=FG, arrowcolor=FG_SOFT, bordercolor=RULE,
                    lightcolor=RULE, darkcolor=RULE, borderwidth=1, padding=5)
    style.map("TCombobox",
              fieldbackground=[("readonly", ENTRY_BG)],
              bordercolor=[("focus", ACCENT)])
    style.configure("TCheckbutton", background=BG, foreground=FG, focuscolor=BG,
                    indicatorcolor=ENTRY_BG, indicatorrelief="flat",
                    bordercolor=RULE, font=FONT)
    style.map("TCheckbutton",
              background=[("active", BG)],
              indicatorcolor=[("selected", ACCENT), ("active", SEL_BG)])
    style.configure("Card.TCheckbutton", background=FRAME_BG)
    style.map("Card.TCheckbutton", background=[("active", FRAME_BG)])

    # Treeview — ruled rows, uppercase sans headings, no heavy borders.
    style.configure("Treeview", background=LIST_BG, fieldbackground=LIST_BG,
                    foreground=FG, borderwidth=0, rowheight=27, font=FONT)
    style.configure("Treeview.Heading", background=BG, foreground=FG_DIM,
                    font=FONT_LABEL, borderwidth=0, relief="flat",
                    padding=(8, 8))
    style.map("Treeview.Heading",
              background=[("active", SEL_BG)],
              foreground=[("active", FG)])
    style.map("Treeview",
              background=[("selected", SEL_BG)],
              foreground=[("selected", FG)])

    style.configure("TProgressbar", background=ACCENT, troughcolor=RULE,
                    borderwidth=0, thickness=4)
    style.configure("TPanedwindow", background=BG)
    style.configure("TSeparator", background=RULE)
    style.configure("Vertical.TScrollbar", background=RULE, troughcolor=BG,
                    borderwidth=0, arrowcolor=FG_SOFT, relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", FG_DIM)])
    style.configure("Horizontal.TScrollbar", background=RULE, troughcolor=BG,
                    borderwidth=0, arrowcolor=FG_SOFT, relief="flat")

    return style
