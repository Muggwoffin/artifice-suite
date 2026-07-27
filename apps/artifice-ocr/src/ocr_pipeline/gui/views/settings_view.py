"""Settings tab: models, endpoints, prompt selection and service health."""

import threading
import tkinter as tk
from tkinter import ttk

from ... import config
from ..._prompts import DOCUMENT_TYPES
from ...config import get as cfg
from .. import theme


class SettingsView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.vars: dict[str, tk.Variable] = {}

        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=16, pady=(12, 0))
        ttk.Label(header, text="Settings", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="Saved to ~/.ocr_pipeline/settings.json",
                  style="Dim.TLabel").pack(side=tk.RIGHT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        self._build_models(body)
        self._build_processing(body)
        self._build_health(body)
        self._build_buttons()

        self.load()

    # ---------------------------------------------------------------- panels
    def _card(self, parent, title: str, col: int, row: int) -> ttk.Frame:
        outer = ttk.Frame(parent, style="Card.TFrame")
        outer.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        ttk.Label(outer, text=title, style="Card.TLabel",
                  font=theme.FONT_HEAD, foreground=theme.ACCENT).pack(
            anchor=tk.W, padx=12, pady=(10, 6))
        inner = ttk.Frame(outer, style="Card.TFrame")
        inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        return inner

    def _entry_row(self, parent, label: str, key: str, width: int = 28):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, style="Card.TLabel", width=17,
                  anchor=tk.W).pack(side=tk.LEFT)
        var = tk.StringVar()
        self.vars[key] = var
        ttk.Entry(row, textvariable=var, width=width).pack(
            side=tk.LEFT, fill=tk.X, expand=True)

    def _check_row(self, parent, label: str, key: str):
        var = tk.BooleanVar()
        self.vars[key] = var
        ttk.Checkbutton(parent, text=label, variable=var,
                        style="Card.TCheckbutton").pack(anchor=tk.W, pady=3)

    def _build_models(self, parent):
        card = self._card(parent, "Models & Connections", col=0, row=0)
        ttk.Label(card, text="Choose which service runs each step, and which model it uses.",
                  style="Card.TLabel", foreground=theme.FG_DIM,
                  font=theme.FONT_SMALL).pack(anchor=tk.W, pady=(0, 6))

        self._combo_row(card, "OCR backend:", "ocr_backend",
                        ["lm_studio", "ollama", "huggingface", "api_key"])
        self._entry_row(card, "OCR model:", "ocr_model")
        self._combo_row(card, "Cleanup backend:", "cleanup_backend",
                        ["ollama", "lm_studio", "huggingface", "api_key"])
        self._entry_row(card, "Cleanup model:", "cleanup_model")
        self._combo_row(card, "Translate backend:", "translate_backend",
                        ["ollama", "lm_studio", "huggingface", "api_key"])
        self._entry_row(card, "Translate model:", "translate_model")

        ttk.Separator(card, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(8, 6))
        ttk.Label(card, text="Connection settings", style="Card.TLabel",
                  font=theme.FONT_SMALL, foreground=theme.FG_DIM).pack(anchor=tk.W)
        self._entry_row(card, "LM Studio URL:", "lm_studio_url")
        self._entry_row(card, "Ollama URL:", "ollama_url")
        self._entry_row(card, "HF token:", "huggingface_token")
        self._entry_row(card, "API key:", "api_key")
        self._entry_row(card, "API base URL:", "api_base_url")

    def _combo_row(self, parent, label: str, key: str, values: list[str]):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, style="Card.TLabel", width=17,
                  anchor=tk.W).pack(side=tk.LEFT)
        var = tk.StringVar()
        self.vars[key] = var
        ttk.Combobox(row, textvariable=var, values=values,
                     state="readonly", width=20).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_processing(self, parent):
        card = self._card(parent, "Processing", col=1, row=0)

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="Document type:", style="Card.TLabel", width=17,
                  anchor=tk.W).pack(side=tk.LEFT)
        self.vars["document_type"] = tk.StringVar()
        combo = ttk.Combobox(row, textvariable=self.vars["document_type"],
                             values=list(DOCUMENT_TYPES.keys()),
                             state="readonly", width=20)
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        combo.bind("<<ComboboxSelected>>", self._on_doc_type)

        self.doc_hint = ttk.Label(card, text="", style="Card.TLabel",
                                  foreground=theme.FG_DIM, font=theme.FONT_SMALL,
                                  wraplength=320, justify=tk.LEFT)
        self.doc_hint.pack(anchor=tk.W, pady=(2, 6))

        self._entry_row(card, "Max OCR workers:", "max_ocr_workers", width=8)
        self._entry_row(card, "Chunk max tokens:", "chunk_max_tokens", width=8)
        self._check_row(card, "Resume (skip existing outputs)", "resume")
        self._check_row(card, "Enable confidence scoring", "confidence_enabled")
        self._check_row(card, "Model reasoning (slow — see README)", "ollama_think")
        ttk.Label(card, text="Reasoning costs ~13x on cleanup for no gain.",
                  style="Card.TLabel", foreground=theme.FG_DIM,
                  font=theme.FONT_SMALL).pack(anchor=tk.W, pady=(0, 2))

        theme_row = ttk.Frame(card, style="Card.TFrame")
        theme_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(theme_row, text="Appearance:", style="Card.TLabel", width=17,
                  anchor=tk.W).pack(side=tk.LEFT)
        self.vars["gui_theme"] = tk.StringVar()
        theme_combo = ttk.Combobox(theme_row, textvariable=self.vars["gui_theme"],
                                   values=["paper", "night"], state="readonly",
                                   width=20)
        theme_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        theme_combo.bind("<<ComboboxSelected>>", self._on_theme)

        self.theme_hint = ttk.Label(card, text="", style="Card.TLabel",
                                    foreground=theme.FG_DIM, font=theme.FONT_SMALL)
        self.theme_hint.pack(anchor=tk.W, pady=(2, 0))

    def _build_health(self, parent):
        card = self._card(parent, "Service Health", col=0, row=1)
        self.health_text = tk.Text(
            card, height=7, bg=theme.LIST_BG, fg=theme.FG, font=theme.FONT_SMALL,
            relief=tk.FLAT, bd=0, state=tk.DISABLED, padx=8, pady=6, wrap=tk.WORD,
        )
        self.health_text.pack(fill=tk.BOTH, expand=True)
        self.health_text.tag_configure("ok", foreground=theme.SUCCESS)
        self.health_text.tag_configure("fail", foreground=theme.ERROR)
        self.health_text.tag_configure("dim", foreground=theme.FG_DIM)

        ttk.Button(card, text="Run pre-flight check",
                   command=self.run_preflight).pack(anchor=tk.W, pady=(8, 0))

    def _build_buttons(self):
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=22, pady=(0, 16))
        ttk.Button(row, text="Save Settings", style="Accent.TButton",
                   command=self.save).pack(side=tk.LEFT)
        ttk.Button(row, text="Reset to Defaults",
                   command=self.reset_defaults).pack(side=tk.LEFT, padx=(8, 0))
        self.saved_label = ttk.Label(row, text="", style="Dim.TLabel")
        self.saved_label.pack(side=tk.LEFT, padx=(12, 0))

    # --------------------------------------------------------------- actions
    def _on_doc_type(self, _event=None):
        key = self.vars["document_type"].get()
        self.doc_hint.configure(text=DOCUMENT_TYPES.get(key, ""))

    def _on_theme(self, _event=None):
        self.theme_hint.configure(
            text="Save, then restart to apply the new appearance.",
            foreground=theme.WARNING,
        )

    def load(self):
        """Populate widgets from the live config."""
        for key, var in self.vars.items():
            value = cfg(key)
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            else:
                var.set("" if value is None else str(value))
        self._on_doc_type()

    def collect(self) -> dict:
        """Read widgets back into a config-shaped dict."""
        out: dict = {}
        for key, var in self.vars.items():
            value = var.get()
            if isinstance(var, tk.BooleanVar):
                out[key] = bool(value)
            elif key in ("max_ocr_workers", "chunk_max_tokens"):
                try:
                    out[key] = int(value)
                except (TypeError, ValueError):
                    continue  # keep the existing value rather than crash the run
            elif value != "":
                out[key] = value
        return out

    def apply_to_config(self) -> dict:
        overrides = self.collect()
        overrides["output_dir"] = self.app.output_var.get()
        config.apply_overrides(overrides)
        return overrides

    def save(self):
        overrides = self.apply_to_config()
        config.save_user_settings(overrides)
        self.saved_label.configure(text="Saved.", foreground=theme.SUCCESS)
        self.after(2500, lambda: self.saved_label.configure(text=""))

    def reset_defaults(self):
        config.reset()
        config.load_config()
        self.load()
        self.saved_label.configure(text="Reset to defaults (not yet saved).",
                                   foreground=theme.WARNING)
        self.after(3000, lambda: self.saved_label.configure(text=""))

    def run_preflight(self):
        self._set_health([("Checking services…", "dim")])
        threading.Thread(target=self._preflight_worker, daemon=True).start()

    def _preflight_worker(self):
        from ...utils import check_lm_studio, check_ollama

        self.apply_to_config()
        backends = {
            cfg("ocr_backend") or "lm_studio",
            cfg("cleanup_backend") or "ollama",
            cfg("translate_backend") or "ollama",
        }
        lines: list[tuple[str, str]] = []

        if "lm_studio" in backends:
            lm_err = check_lm_studio(cfg("lm_studio_url"))
            lines.append(
                (f"LM Studio   FAIL  {lm_err}", "fail") if lm_err
                else (f"LM Studio   OK    {cfg('lm_studio_url')}", "ok")
            )

        if "ollama" in backends:
            models = [cfg("ocr_model"), cfg("cleanup_model"), cfg("translate_model")]
            ollama_url = cfg("ollama_url")
            errors = check_ollama(models, url=ollama_url)
            if any("Cannot reach" in e for e in errors):
                lines.append((f"Ollama      FAIL  {errors[0]}", "fail"))
            else:
                lines.append(("Ollama      OK", "ok"))
                for model in models:
                    if not model:
                        continue
                    err = next((e for e in errors if model in e), None)
                    lines.append(
                        (f"  Model     FAIL  {model}", "fail") if err
                        else (f"  Model     OK    {model}", "ok")
                    )

        if "huggingface" in backends:
            token = cfg("huggingface_token")
            lines.append(
                ("Hugging Face   FAIL  No token configured", "fail") if not token
                else ("Hugging Face   OK", "ok")
            )

        if "api_key" in backends:
            api_key = cfg("api_key")
            base_url = cfg("api_base_url") or "https://api.openai.com/v1"
            if not api_key:
                lines.append(("API Key      FAIL  No key configured", "fail"))
            else:
                try:
                    from openai import OpenAI
                    client = OpenAI(base_url=base_url, api_key=api_key)
                    client.models.list()
                    lines.append((f"API Key      OK    {base_url}", "ok"))
                except Exception as exc:
                    lines.append((f"API Key      FAIL  {exc}", "fail"))

        self.after(0, lambda: self._set_health(lines))

    def _set_health(self, lines: list[tuple[str, str]]):
        self.health_text.configure(state=tk.NORMAL)
        self.health_text.delete("1.0", tk.END)
        for text, tag in lines:
            self.health_text.insert(tk.END, text + "\n", tag)
        self.health_text.configure(state=tk.DISABLED)
