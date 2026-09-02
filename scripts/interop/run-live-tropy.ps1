# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

[CmdletBinding()]
param(
    [ValidateSet("stable", "canary")]
    [string]$Channel = "stable",
    [string]$TropySource,
    [string]$TropyExecutable,
    [string]$NodeExecutable = "node",
    [string]$TempRoot
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $TropySource) {
    $TropySource = Join-Path $RepoRoot ".interop\tropy-$Channel"
}

$Required = @(
    (Join-Path $TropySource "scripts\db.js"),
    (Join-Path $TropySource "lib\main\index.js")
)
foreach ($Path in $Required) {
    if (-not (Test-Path $Path -PathType Leaf)) {
        throw "Tropy's native Windows source build is incomplete: $Path"
    }
}
if (-not (Get-Command $NodeExecutable -ErrorAction SilentlyContinue)) {
    throw "Node is unavailable: $NodeExecutable"
}
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    throw "uv is unavailable"
}

if ($TropyExecutable -and -not (Test-Path $TropyExecutable -PathType Leaf)) {
    throw "Tropy executable does not exist: $TropyExecutable"
}

$OldLive = $env:ARTIFICE_LIVE_TROPY
$OldSource = $env:ARTIFICE_TROPY_SOURCE
$OldExecutable = $env:ARTIFICE_TROPY_EXECUTABLE
$OldNode = $env:ARTIFICE_TROPY_NODE
$OldTemp = $env:TEMP
$OldTmp = $env:TMP

try {
    $env:ARTIFICE_LIVE_TROPY = "1"
    $env:ARTIFICE_TROPY_SOURCE = $TropySource
    $env:ARTIFICE_TROPY_NODE = (Get-Command $NodeExecutable).Source
    if ($TropyExecutable) {
        $env:ARTIFICE_TROPY_EXECUTABLE = (Resolve-Path $TropyExecutable).Path
    }
    if ($TempRoot) {
        $ResolvedTemp = (Resolve-Path $TempRoot).Path
        $env:TEMP = $ResolvedTemp
        $env:TMP = $ResolvedTemp
    }
    Set-Location $RepoRoot
    & uv run pytest -m live_interop apps/artifice-ocr/tests/test_tropy_live.py -v
    if ($LASTEXITCODE -ne 0) {
        throw "Live Tropy contract failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:ARTIFICE_LIVE_TROPY = $OldLive
    $env:ARTIFICE_TROPY_SOURCE = $OldSource
    $env:ARTIFICE_TROPY_EXECUTABLE = $OldExecutable
    $env:ARTIFICE_TROPY_NODE = $OldNode
    $env:TEMP = $OldTemp
    $env:TMP = $OldTmp
}
