# Windows Defender false-positive mitigation

`artifice-ocr.exe` is built with PyInstaller. Defender's
`Behavior:Win32/DefenseEvasion.A!ml` heuristic is sensitive to a combination
of packed bootloaders, hidden child processes, process-table inspection, and
runtime modification of downloaded files. The OCR runtime and spec avoid
those patterns now.

## Runtime policy

- Tesseract is launched with an argument list and `shell=False`; its temporary
  PNG is input data only and is removed after the process exits.
- Tropy write-back uses its SQLite lock probe. It does not enumerate the host
  process table or create a hidden `tasklist`/`pgrep` child process.
- Native file reveal uses `os.startfile` on Windows and validated, non-shell
  argv on macOS/Linux.
- Frozen startup never removes `Zone.Identifier` alternate-data streams. This
  metadata is a Windows security signal and must be handled by the installer
  or the user, not by the application.
- PowerShell is used only by `secure-io` to read ACLs; it runs with
  `-NoProfile -NonInteractive` and does not bypass execution policy.

## Build policy

The OCR spec is an onedir build with `upx=False` and `console=False`. It also
includes only the pywebview backend for the target platform, rather than
shipping every GUI backend and pythonnet in every executable. These choices
make the bundle less opaque and reduce heuristic noise; they do not weaken
the application's file or database permissions.

## Release checklist

1. Build on a native Windows runner with the checked-in spec (`pyinstaller
   --clean --noconfirm apps/artifice-ocr/artifice-ocr.spec`).
2. Inspect the output with `sigcheck -m -i` or `dumpbin /headers`; verify that
   the executable has normal version metadata and no unexpected packer.
3. Authenticode-sign the executable and shipped DLLs with the organisation's
   code-signing certificate (prefer a hardware-backed/SignPath or Azure
     Key Vault workflow). Timestamp the signature, then verify with
   `signtool verify /pa /all /v`.
4. Distribute the signed onedir folder in a signed installer or a release
   archive. Do not ask the application to clear Mark-of-the-Web; if an
   unsigned archive is used for internal testing, Windows' documented
   **Properties → Unblock** action applies to the archive before extraction.
5. Submit the signed hash and the Defender detection to Microsoft Security
   Intelligence when the heuristic persists. A clean, reproducible build,
   stable publisher identity, and a signed artifact are the durable fixes;
   changing strings or adding obfuscation is not.

