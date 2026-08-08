# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

# iexpress-transcribe.sed — Self-Extraction Directive for IExpress (Windows).
#
# MAINTAINER: Run this on Windows to compile a hidden Setup.exe:
#
#   iexpress /n scripts\iexpress-transcribe.sed
#
# The /n flag opens the IExpress Wizard with this SED file pre-loaded.
# The Wizard has two remaining pages (package name, finished message) that
# still require manual confirmation — there is no fully unattended /q mode
# in the version of IExpress shipped with Windows 10/11.  The pre-filled
# fields minimise the chance of misconfiguration.
#
# When compiled, the resulting Setup.exe will:
#   1. Silently extract launch-transcribe.bat and install.ps1 to a temp dir.
#   2. Run launch-transcribe.bat (which hides the terminal and calls
#      install.ps1 with Bypass).
#   3. Remove the temp files after the installer exits.

[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=cmd /c launch-transcribe.bat
PostInstallCmd=
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles
ExtractOnly=1
ExtractDirectory=%temp%\artifice-transcribe-install

[SourceFiles]
SourceFiles0=launch-transcribe.bat
SourceFiles1=install.ps1

[SourceFilesSource]
SourceFilesSource0=%CWD%
SourceFilesSource1=%CWD%
