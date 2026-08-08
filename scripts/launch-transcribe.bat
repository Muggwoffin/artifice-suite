@echo off

REM SPDX-FileCopyrightText: 2026 Maurice Casey
REM
REM SPDX-License-Identifier: AGPL-3.0-or-later

REM launch-transcribe.bat — "spoof" launcher for the Artifice Transcribe installer.
REM
REM Double-click this batch file to run install.ps1 with no visible terminal
REM window and no execution-policy prompt.  It resolves its own directory so
REM the batch file and install.ps1 can be shipped together in a self-extracting
REM archive.

PowerShell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0install.ps1"
