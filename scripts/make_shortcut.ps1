<#
.SYNOPSIS
    Create the "Copy Editor" desktop shortcut.

.DESCRIPTION
    Writes "Copy Editor.lnk" into the project root, pointing at the windowed
    Python interpreter (pythonw.exe) best able to run the tool. Drag the
    result onto your Desktop, or pass -Desktop to place a copy there directly.

    Interpreter choice prefers one that also has tkinterdnd2, since that is
    what enables drag-and-drop; the tool still runs without it, using a file
    picker instead.

    Re-run this after moving the project or reinstalling Python: the shortcut
    stores an absolute path to the interpreter, which the launcher cannot
    repair by itself once it is gone.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1
    powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1 -Desktop
#>
[CmdletBinding()]
param(
    [switch]$Desktop
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root "launch_copyedit.pyw"
$icon = Join-Path $root "assets\copyedit.ico"

if (-not (Test-Path $launcher)) {
    throw "Launcher not found: $launcher"
}

$required = "docx, docx_revisions, requests, tkinter"
$preferred = "$required, tkinterdnd2"

$candidates = @()
try {
    foreach ($line in (& py -0p 2>$null)) {
        $idx = $line.IndexOf("C:\")
        if ($idx -ge 0) { $candidates += $line.Substring($idx).Trim().Trim('"') }
    }
} catch {
    Write-Warning "The 'py' launcher is unavailable; falling back to PATH."
}
$candidates += @((Get-Command python.exe -ErrorAction SilentlyContinue).Source)
$candidates = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

# Probing prints a traceback for each interpreter that lacks a package. In
# Windows PowerShell, redirecting a native command's stderr wraps every line in
# an ErrorRecord, which $ErrorActionPreference='Stop' then treats as fatal - so
# relax it for the probe and rely on $LASTEXITCODE instead.
function Test-Imports([string]$Exe, [string]$Modules) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Exe -c "import $Modules" 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $previous
    }
}

$chosen = $null
foreach ($exe in $candidates) {
    if (Test-Imports $exe $preferred) { $chosen = $exe; break }
}
if (-not $chosen) {
    foreach ($exe in $candidates) {
        if (Test-Imports $exe $required) {
            $chosen = $exe
            Write-Warning "No interpreter has tkinterdnd2 - drag-and-drop will be unavailable (file picker still works)."
            break
        }
    }
}
if (-not $chosen) {
    throw "No installed Python has the dependencies. Run 'pip install -r requirements.txt' in $root first."
}

$windowed = Join-Path (Split-Path $chosen) "pythonw.exe"
$target = if (Test-Path $windowed) { $windowed } else { $chosen }
Write-Host "Interpreter : $target"

if (-not (Test-Path $icon)) {
    Write-Host "Icon missing - generating it..."
    & $chosen (Join-Path $root "scripts\make_icon.py")
}

function New-AppShortcut([string]$Path) {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($Path)
    $sc.TargetPath = $target
    $sc.Arguments = '"' + $launcher + '"'
    $sc.WorkingDirectory = $root
    $sc.Description = "Copy Editor - tracked-change copy editing with a local LLM"
    $sc.WindowStyle = 1
    if (Test-Path $icon) { $sc.IconLocation = "$icon,0" }
    $sc.Save()
    Write-Host "Created     : $Path"
}

New-AppShortcut (Join-Path $root "Copy Editor.lnk")

if ($Desktop) {
    New-AppShortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Copy Editor.lnk")
} else {
    Write-Host ""
    Write-Host "Drag 'Copy Editor.lnk' onto your Desktop, or re-run with -Desktop."
}
