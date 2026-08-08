(*
SPDX-FileCopyrightText: 2026 Maurice Casey

SPDX-License-Identifier: AGPL-3.0-or-later

Install-transcribe.applescript — macOS "spoof" launcher for the Artifice
Transcribe installer.

MAINTAINER: Open this file in Script Editor (in /Applications/Utilities/),
then choose File > Export.  Set:

  File Format:  Application
  Options:      [x] Stay open after run handler

This creates an "Install-transcribe.app" bundle in Finder.  Double-clicking
it runs install.sh with administrator privileges, which triggers the macOS
admin password dialog, giving a native installer feel.

The path to install.sh is relative to this script's location.  Adjust it
below if you move the files.  When bundled as an .app by Script Editor,
the ``path to me`` idiom resolves to the .app bundle, so the relative path
below assumes install.sh lives in the same directory as the .app.
*)

-- Resolve the directory containing this script (or .app bundle).
-- When run from Script Editor, (path to me) returns the .app path.
set scriptDir to do shell script "dirname " & quoted form of (POSIX path of (path to me))
set installerPath to scriptDir & "/install.sh"

-- Run the installer.  "with administrator privileges" triggers the standard
-- macOS admin password dialog.
do shell script "bash " & quoted form of installerPath with administrator privileges
