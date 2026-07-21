import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"}

TITLE = "OCR Pipeline — Historical Document Processor"
WINDOW_SIZE = "820x720"
BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
ACCENT_DIM = "#45475a"
SUCCESS = "#a6e3a1"
WARNING = "#f9e2af"
ENTRY_BG = "#313244"
FRAME_BG = "#181825"
LIST_BG = "#11111b"
FONT = ("Consolas", 10)
FONT_BOLD = ("Consolas", 10, "bold")
FONT_TITLE = ("Segoe UI", 14, "bold")


class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITLE)
        self.geometry(WINDOW_SIZE)
        self.configure(bg=BG)
        self.minsize(700, 580)

        self.files: list[str] = []
        self._build_ui()
        self._update_file_count()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=16, pady=(12, 0))

        tk.Label(top, text="OCR Pipeline", font=FONT_TITLE, bg=BG, fg=ACCENT).pack(
            side=tk.LEFT
        )

        tk.Label(
            top,
            text="Drop image files below, or click Browse",
            font=FONT,
            bg=BG,
            fg=FG,
        ).pack(side=tk.RIGHT)

        self._build_drop_zone()
        self._build_file_list()
        self._build_controls()
        self._build_settings_panel()
        self._build_log_area()
        self._build_status_bar()

    # ---- drop zone -------------------------------------------------------
    def _build_drop_zone(self):
        self.drop_frame = tk.Frame(self, bg=ACCENT_DIM, bd=2, relief=tk.DASHED)
        self.drop_frame.pack(fill=tk.X, padx=16, pady=(12, 0))

        self.drop_label = tk.Label(
            self.drop_frame,
            text="\u2b07  Drop files here  \u2b07",
            font=FONT_BOLD,
            bg=ACCENT_DIM,
            fg=ACCENT,
            pady=14,
        )
        self.drop_label.pack(fill=tk.X, padx=4, pady=4)

        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)

        self.drop_label.bind("<Button-1>", lambda _: self._browse_files())

    # ---- file list -------------------------------------------------------
    def _build_file_list(self):
        list_frame = tk.Frame(self, bg=BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 0))

        self.file_listbox = tk.Listbox(
            list_frame,
            bg=LIST_BG,
            fg=FG,
            font=FONT,
            selectbackground=ACCENT,
            selectforeground=BG,
            activestyle="none",
            relief=tk.FLAT,
            bd=0,
            height=8,
        )
        scrollbar = ttk.Scrollbar(list_frame, command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill=tk.X, padx=16, pady=(4, 0))

        tk.Button(
            btn_row,
            text="Browse Files",
            command=self._browse_files,
            bg=ACCENT_DIM,
            fg=FG,
            activebackground=ACCENT,
            activeforeground=BG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=3,
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_row,
            text="Remove Selected",
            command=self._remove_selected,
            bg=ACCENT_DIM,
            fg=FG,
            activebackground="#f38ba8",
            activeforeground=BG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=3,
        ).pack(side=tk.LEFT, padx=(6, 0))

        tk.Button(
            btn_row,
            text="Clear All",
            command=self._clear_files,
            bg=ACCENT_DIM,
            fg=FG,
            activebackground="#f38ba8",
            activeforeground=BG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=3,
        ).pack(side=tk.LEFT, padx=(6, 0))

        self.file_count_label = tk.Label(
            btn_row, text="", font=FONT, bg=BG, fg=FG
        )
        self.file_count_label.pack(side=tk.RIGHT)

    # ---- controls --------------------------------------------------------
    def _build_controls(self):
        ctrl = tk.Frame(self, bg=BG)
        ctrl.pack(fill=tk.X, padx=16, pady=(10, 0))

        # stages
        tk.Label(ctrl, text="Stages:", font=FONT_BOLD, bg=BG, fg=FG).pack(
            side=tk.LEFT
        )

        self.var_ocr = tk.BooleanVar(value=True)
        self.var_cleanup = tk.BooleanVar(value=True)
        self.var_translate = tk.BooleanVar(value=False)
        self.var_force = tk.BooleanVar(value=False)

        for text, var in [
            ("OCR", self.var_ocr),
            ("Cleanup", self.var_cleanup),
            ("Translate", self.var_translate),
            ("Force", self.var_force),
        ]:
            cb = tk.Checkbutton(
                ctrl,
                text=text,
                variable=var,
                font=FONT,
                bg=BG,
                fg=FG,
                selectcolor=ACCENT_DIM,
                activebackground=BG,
                activeforeground=FG,
            )
            cb.pack(side=tk.LEFT, padx=(10, 0))

        # output dir
        out_frame = tk.Frame(self, bg=BG)
        out_frame.pack(fill=tk.X, padx=16, pady=(8, 0))

        tk.Label(out_frame, text="Output:", font=FONT_BOLD, bg=BG, fg=FG).pack(
            side=tk.LEFT
        )

        self.output_var = tk.StringVar(value="output")
        self.output_entry = tk.Entry(
            out_frame,
            textvariable=self.output_var,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            font=FONT,
            relief=tk.FLAT,
        )
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))

        tk.Button(
            out_frame,
            text="...",
            command=self._browse_output_dir,
            bg=ACCENT_DIM,
            fg=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=6,
        ).pack(side=tk.LEFT)

        # run button
        self.run_btn = tk.Button(
            out_frame,
            text="\u25b6  Run Pipeline",
            command=self._run_pipeline,
            bg=ACCENT,
            fg=BG,
            activebackground=SUCCESS,
            activeforeground=BG,
            font=FONT_BOLD,
            relief=tk.FLAT,
            padx=14,
            pady=3,
        )
        self.run_btn.pack(side=tk.RIGHT)

    # ---- settings panel --------------------------------------------------
    def _build_settings_panel(self):
        self.settings_visible = False

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill=tk.X, padx=16, pady=(6, 0))

        self.settings_toggle = tk.Button(
            btn_row,
            text="\u25b6 Settings",
            command=self._toggle_settings,
            bg=ACCENT_DIM,
            fg=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=8,
            pady=2,
        )
        self.settings_toggle.pack(side=tk.LEFT)

        self.settings_frame = tk.Frame(self, bg=FRAME_BG, bd=1, relief=tk.GROOVE)

        from src.ocr_pipeline.config import get as cfg_default

        fields = [
            ("LM Studio URL:", "settings_lm_url", cfg_default("lm_studio_url")),
            ("OCR Model:", "settings_ocr_model", cfg_default("ocr_model")),
            ("Cleanup Model:", "settings_cleanup_model", cfg_default("cleanup_model")),
            ("Translate Model:", "settings_translate_model", cfg_default("translate_model")),
            ("Max Workers:", "settings_max_workers", str(cfg_default("max_ocr_workers"))),
        ]

        for label_text, attr_name, default_val in fields:
            row = tk.Frame(self.settings_frame, bg=FRAME_BG)
            row.pack(fill=tk.X, padx=8, pady=2)
            tk.Label(row, text=label_text, font=FONT, bg=FRAME_BG, fg=FG, width=16, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar(value=default_val)
            setattr(self, attr_name, var)
            entry = tk.Entry(
                row,
                textvariable=var,
                bg=ENTRY_BG,
                fg=FG,
                insertbackground=FG,
                font=FONT,
                relief=tk.FLAT,
            )
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        resume_row = tk.Frame(self.settings_frame, bg=FRAME_BG)
        resume_row.pack(fill=tk.X, padx=8, pady=(2, 4))
        self.settings_resume = tk.BooleanVar(value=cfg_default("resume"))
        tk.Checkbutton(
            resume_row,
            text="Resume (skip existing outputs)",
            variable=self.settings_resume,
            font=FONT,
            bg=FRAME_BG,
            fg=FG,
            selectcolor=ACCENT_DIM,
            activebackground=FRAME_BG,
            activeforeground=FG,
        ).pack(side=tk.LEFT)

        # Document type dropdown
        doc_type_row = tk.Frame(self.settings_frame, bg=FRAME_BG)
        doc_type_row.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(doc_type_row, text="Document Type:", font=FONT, bg=FRAME_BG, fg=FG, width=16, anchor=tk.W).pack(side=tk.LEFT)

        from src.ocr_pipeline._prompts import DOCUMENT_TYPES
        self.settings_doc_type = tk.StringVar(value=cfg_default("document_type"))
        doc_type_menu = ttk.Combobox(
            doc_type_row,
            textvariable=self.settings_doc_type,
            values=list(DOCUMENT_TYPES.keys()),
            state="readonly",
            font=FONT,
            width=18,
        )
        doc_type_menu.pack(side=tk.LEFT, padx=(4, 0))

        # Confidence toggle
        conf_row = tk.Frame(self.settings_frame, bg=FRAME_BG)
        conf_row.pack(fill=tk.X, padx=8, pady=(2, 6))
        self.settings_confidence = tk.BooleanVar(value=cfg_default("confidence_enabled"))
        tk.Checkbutton(
            conf_row,
            text="Enable confidence scoring",
            variable=self.settings_confidence,
            font=FONT,
            bg=FRAME_BG,
            fg=FG,
            selectcolor=ACCENT_DIM,
            activebackground=FRAME_BG,
            activeforeground=FG,
        ).pack(side=tk.LEFT)

    def _toggle_settings(self):
        if self.settings_visible:
            self.settings_frame.pack_forget()
            self.settings_toggle.config(text="\u25b6 Settings")
            self.settings_visible = False
        else:
            self.settings_frame.pack(fill=tk.X, padx=16, pady=(4, 0), after=self.winfo_children()[3])
            self.settings_toggle.config(text="\u25bc Settings")
            self.settings_visible = True

    def _apply_settings(self):
        """Apply GUI settings to the runtime config."""
        from src.ocr_pipeline import config
        overrides = {}
        if self.settings_lm_url.get():
            overrides["lm_studio_url"] = self.settings_lm_url.get()
        if self.settings_ocr_model.get():
            overrides["ocr_model"] = self.settings_ocr_model.get()
        if self.settings_cleanup_model.get():
            overrides["cleanup_model"] = self.settings_cleanup_model.get()
        if self.settings_translate_model.get():
            overrides["translate_model"] = self.settings_translate_model.get()
        try:
            overrides["max_ocr_workers"] = int(self.settings_max_workers.get())
        except ValueError:
            pass
        overrides["resume"] = self.settings_resume.get()
        overrides["document_type"] = self.settings_doc_type.get()
        overrides["confidence_enabled"] = self.settings_confidence.get()
        config.apply_overrides(overrides)

    # ---- log area --------------------------------------------------------
    def _build_log_area(self):
        self.log = scrolledtext.ScrolledText(
            self,
            bg=LIST_BG,
            fg=FG,
            font=FONT,
            height=10,
            relief=tk.FLAT,
            bd=0,
            state=tk.DISABLED,
            insertbackground=FG,
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=16, pady=(10, 0))
        self.log.tag_configure("success", foreground=SUCCESS)
        self.log.tag_configure("warning", foreground=WARNING)
        self.log.tag_configure("accent", foreground=ACCENT)

    # ---- status bar ------------------------------------------------------
    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="Ready")
        bar = tk.Frame(self, bg=ACCENT_DIM)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(
            bar,
            textvariable=self.status_var,
            font=FONT,
            bg=ACCENT_DIM,
            fg=FG,
            anchor=tk.W,
            padx=10,
            pady=3,
        ).pack(fill=tk.X)

    # -------------------------------------------------------------- actions
    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        added = 0
        for p in paths:
            pp = Path(p)
            if pp.is_dir():
                for f in sorted(pp.iterdir()):
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                        fp = str(f)
                        if fp not in self.files:
                            self.files.append(fp)
                            added += 1
            elif pp.suffix.lower() in SUPPORTED_EXTENSIONS and p not in self.files:
                self.files.append(p)
                added += 1
        self._refresh_list()
        if added:
            self._log(f"Added {added} file(s) via drag-and-drop", "accent")

    def _browse_files(self):
        filepaths = filedialog.askopenfilenames(
            title="Select document files",
            filetypes=[
                ("Documents", "*.jpg *.jpeg *.png *.tif *.tiff *.pdf"),
                ("Image files", "*.jpg *.jpeg *.png *.tif *.tiff"),
                ("PDF files", "*.pdf"),
                ("All files", "*.*"),
            ],
        )
        added = 0
        for p in filepaths:
            if p not in self.files:
                self.files.append(p)
                added += 1
        self._refresh_list()
        if added:
            self._log(f"Added {added} file(s) via browse", "accent")

    def _remove_selected(self):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        for i in reversed(sel):
            self.file_listbox.delete(i)
            del self.files[i]
        self._update_file_count()

    def _clear_files(self):
        self.files.clear()
        self._refresh_list()

    def _browse_output_dir(self):
        d = filedialog.askdirectory(title="Select output directory")
        if d:
            self.output_var.set(d)

    # -------------------------------------------------------------- helpers
    def _refresh_list(self):
        self.file_listbox.delete(0, tk.END)
        for p in self.files:
            self.file_listbox.insert(tk.END, Path(p).name)
        self._update_file_count()

    def _update_file_count(self):
        n = len(self.files)
        self.file_count_label.config(text=f"{n} file{'s' if n != 1 else ''}")

    def _log(self, msg: str, tag: str = ""):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n", tag)
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    # ----------------------------------------------------------- pipeline run
    def _run_pipeline(self):
        if not self.files:
            messagebox.showwarning("No files", "Add at least one image file to process.")
            return

        stages = []
        if self.var_ocr.get():
            stages.append("ocr")
        if self.var_cleanup.get():
            stages.append("cleanup")
        if self.var_translate.get():
            stages.append("translate")

        if not stages:
            messagebox.showwarning("No stages", "Enable at least one pipeline stage.")
            return

        self._apply_settings()

        output_dir = self.output_var.get()
        self.run_btn.config(state=tk.DISABLED)
        self.status_var.set("Running...")
        self._log(f"Pipeline start — {len(self.files)} file(s), stages: {', '.join(stages)}", "accent")

        thread = threading.Thread(
            target=self._pipeline_worker,
            args=(stages, output_dir, self.var_force.get()),
            daemon=True,
        )
        thread.start()

    def _pipeline_worker(self, stages: list[str], output_dir: str, force: bool):
        try:
            from src.ocr_pipeline.config import get as cfg
            resume = cfg("resume") and not force

            skip_ocr = "ocr" not in stages
            skip_cleanup = "cleanup" not in stages
            skip_translate = "translate" not in stages

            if "ocr" in stages:
                from src.ocr_pipeline.stages import ocr as ocr_stage
                from src.ocr_pipeline.pipeline import _output_exists

                for path in self.files:
                    stem = Path(path).stem
                    if resume and _output_exists("raw_ocr", stem, output_dir):
                        self._after(lambda p=path: self._log(f"[OCR] {Path(p).name} [skipped]", "warning"))
                        from src.ocr_pipeline.pipeline import _load_existing_text
                        text = _load_existing_text("raw_ocr", stem, output_dir)
                        result = {"extracted_text": text, "source_file": path, "stage": "raw_ocr"}
                    else:
                        self._after(lambda p=path: self._log(f"[OCR] {Path(p).name} ..."))
                        result = ocr_stage.perform(path, output_dir=output_dir)

                    self._after(
                        lambda r=result, p=path: self._log(
                            f"[OCR] {Path(p).name} -> {len(r['extracted_text'])} chars",
                            "success",
                        )
                    )
                    if "cleanup" in stages or "translate" in stages:
                        self._run_downstream(path, result, stages, output_dir, resume)
            else:
                self._after(lambda: self._log("[OCR] Skipped", "warning"))
                if "cleanup" in stages or "translate" in stages:
                    for path in self.files:
                        stem = Path(path).stem
                        result = {"extracted_text": "(OCR skipped)", "source_file": path, "stage": "raw_ocr"}
                        self._run_downstream(path, result, stages, output_dir, resume)
        except Exception as exc:
            self._after(lambda e=exc: self._log(f"ERROR: {e}", "warning"))
        finally:
            self._after(self._pipeline_done)

    def _run_downstream(self, ocr_path, ocr_result, stages, output_dir, resume=True):
        from src.ocr_pipeline.pipeline import _output_exists, _load_existing_text

        raw_text = ocr_result["extracted_text"]
        source = ocr_result["source_file"]
        stem = Path(ocr_path).stem

        if "cleanup" in stages:
            from src.ocr_pipeline.stages import cleanup as cleanup_stage

            if resume and _output_exists("cleaned", stem, output_dir):
                self._after(lambda p=ocr_path: self._log(f"[Cleanup] {Path(p).name} [skipped]", "warning"))
                text = _load_existing_text("cleaned", stem, output_dir)
                result = {"cleaned_text": text, "raw_text": raw_text, "source_file": source, "stage": "cleaned"}
            else:
                self._after(lambda p=ocr_path: self._log(f"[Cleanup] {Path(p).name} ..."))
                result = cleanup_stage.perform(
                    raw_text, source_file=source, output_dir=output_dir
                )

            self._after(
                lambda r=result, p=ocr_path: self._log(
                    f"[Cleanup] {Path(p).name} -> {len(r['cleaned_text'])} chars",
                    "success",
                )
            )
            if "translate" in stages:
                self._run_translate(ocr_path, result, output_dir, resume)
        elif "translate" in stages:
            self._after(lambda: self._log("[Translate] Skipped (no cleanup input)", "warning"))

    def _run_translate(self, ocr_path, cleanup_result, output_dir, resume=True):
        from src.ocr_pipeline.stages import translate as translate_stage
        from src.ocr_pipeline.pipeline import _output_exists, _load_existing_text

        stem = Path(ocr_path).stem

        if resume and _output_exists("translated", stem, output_dir):
            self._after(lambda p=ocr_path: self._log(f"[Translate] {Path(p).name} [skipped]", "warning"))
            text = _load_existing_text("translated", stem, output_dir)
            result = {"translated_text": text, "cleaned_text": cleanup_result["cleaned_text"],
                      "source_file": cleanup_result["source_file"], "stage": "translated"}
        else:
            self._after(lambda p=ocr_path: self._log(f"[Translate] {Path(p).name} ..."))
            result = translate_stage.perform(
                cleanup_result["cleaned_text"],
                source_file=cleanup_result["source_file"],
                output_dir=output_dir,
            )

        self._after(
            lambda r=result, p=ocr_path: self._log(
                f"[Translate] {Path(p).name} -> {len(r.get('translated_text', ''))} chars",
                "success",
            )
        )

    def _after(self, fn):
        self.after(0, fn)

    def _pipeline_done(self):
        self.run_btn.config(state=tk.NORMAL)
        self.status_var.set("Done")
        self._log("---", "")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
