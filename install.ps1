# M.I.N.D installer: double-click install.bat (it runs this). Safe to run again: finished steps are skipped.
# Installs what's missing (Python 3.10, Node.js, Git, Chrome) with winget, sets up M.I.N.D's Python and HUD,
# adds the Start menu button + start with Windows, then starts M.I.N.D (its setup screen opens by itself).
# -TestOnly: only Python packages + HUD build, no shortcuts, no start (used to test the installer).
param([switch]$TestOnly)
$ErrorActionPreference = "Continue"  # (PS 5.1 treats a program writing to stderr as an error; exit codes are checked instead)
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Log = Join-Path $Root "install_log.txt"
Start-Transcript -Path $Log -Force | Out-Null

function Say($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) {
    Write-Host ""; Write-Host "PROBLEM: $text" -ForegroundColor Red
    Write-Host "Send the file install_log.txt (in this folder) to whoever shared M.I.N.D with you." -ForegroundColor Yellow
    Stop-Transcript | Out-Null; exit 1
}
function Refresh-Path {
    # A program winget just installed isn't on this window's PATH yet: read it again from Windows
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Winget-Install($id, $name) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "winget is missing. Update 'App Installer' from the Microsoft Store, then run install.bat again."
    }
    Say "Installing $name (free). If Windows asks to allow changes, click Yes."
    & winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
}
function Run($what, [scriptblock]$block) {
    & $block
    if ($LASTEXITCODE -ne 0) { Fail "$what failed (exit code $LASTEXITCODE)." }
}

Write-Host "M.I.N.D installer" -ForegroundColor Cyan
# Run straight from inside the ZIP, Windows unpacks it into a Temp folder that is deleted later
if ($Root -match "\\Temp\\" -and $Root -match "\.zip") {
    Fail "You opened install.bat from INSIDE the ZIP. Close this, right-click the ZIP, Extract All..., then double-click install.bat in the extracted folder."
}
Write-Host "This takes about 10-15 minutes the first time (it downloads about 1 GB). Keep this window open."

# ---------- 1. Python 3.10 (M.I.N.D's parts are tested on 3.10) ----------
function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $found = & py -3.10 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $found) { return $found.Trim() }
    }
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python310\python.exe", "$env:ProgramFiles\Python310\python.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}
$Python = Find-Python
if (-not $Python) {
    Winget-Install "Python.Python.3.10" "Python 3.10"
    $Python = Find-Python
    if (-not $Python) { Fail "Python 3.10 didn't install. Install it from python.org (3.10), then run install.bat again." }
}
Say "Python: $Python"

# ---------- 2. Node.js (builds the HUD), Git (updates), Chrome (HUD, phone app, extension) ----------
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Winget-Install "OpenJS.NodeJS.LTS" "Node.js"
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { Fail "Node.js didn't install. Install it from nodejs.org (LTS), then run install.bat again." }
}
if (-not $TestOnly -and -not (Get-Command git -ErrorAction SilentlyContinue)) { Winget-Install "Git.Git" "Git" }
$Chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $TestOnly -and -not $Chrome) { Winget-Install "Google.Chrome" "Google Chrome" }

# ---------- 3. M.I.N.D's own Python (backend\venv) with the exact tested packages ----------
$Venv = Join-Path $Backend "venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Say "Making M.I.N.D's Python folder..."
    Run "Making the Python folder" { & $Python -m venv $Venv }
}
Say "Installing M.I.N.D's Python parts (the longest step)..."
Run "Updating pip" { & $VenvPython -m pip install --upgrade pip --quiet --disable-pip-version-check }
Run "Installing Python parts" { & $VenvPython -m pip install -r (Join-Path $Backend "requirements-lock.txt") --disable-pip-version-check }

Say "Downloading the wake word and voice models..."
Push-Location $Backend
try {
    foreach ($try in 1..3) {
        & $VenvPython prefetch.py
        if ($LASTEXITCODE -eq 0) { break }
        if ($try -eq 3) { Fail "Downloading M.I.N.D's models failed. Check the internet and run install.bat again." }
        Say "The download dropped, trying again ($try of 3)..."; Start-Sleep -Seconds 5
    }
} finally { Pop-Location }

# ---------- 4. The HUD ----------
Say "Building the HUD..."
Push-Location $Root
try {
    # Electron (only for Jarvis mode, ~110 MB) is fetched separately below, so a dropped download can't stop the install
    $env:ELECTRON_SKIP_BINARY_DOWNLOAD = "1"
    foreach ($try in 1..3) {  # (slow or shaky internet: try again)
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -eq 0) { break }
        if ($try -eq 3) { Fail "Installing the HUD's parts failed (exit code $LASTEXITCODE). Check the internet and run install.bat again." }
        Say "The download dropped, trying again ($try of 3)..."; Start-Sleep -Seconds 5
    }
    Remove-Item Env:ELECTRON_SKIP_BINARY_DOWNLOAD
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path (Join-Path $Root "dist\index.html")) { Say "Couldn't rebuild the HUD, using the ready-made one." }
        else { Fail "Building the HUD failed (exit code $LASTEXITCODE)." }
    }
    Say "Getting Jarvis mode (optional)..."
    foreach ($try in 1..3) {
        & node (Join-Path $Root "node_modules\electron\install.js")
        if ($LASTEXITCODE -eq 0) { break }
        if ($try -eq 3) { Write-Host "Jarvis mode didn't download (internet). Everything else works; run install.bat again later to add it." -ForegroundColor Yellow }
        else { Start-Sleep -Seconds 5 }
    }
} finally { Pop-Location }

# ---------- 5. Keys file (the setup screen fills it in) ----------
$Env = Join-Path $Backend ".env"
if (-not (Test-Path $Env)) { Copy-Item (Join-Path $Backend ".env.example") $Env }

if ($TestOnly) { Say "Test install finished."; Stop-Transcript | Out-Null; exit 0 }

# ---------- 6. Start menu button, start with Windows, and start M.I.N.D ----------
Say "Adding the M.I.N.D button and starting with Windows..."
Push-Location $Backend
try {
    Run "Start menu button" { & $VenvPython autostart.py button }
    Run "Hiding the black window" { & $VenvPython autostart.py hide }
    Run "Start with Windows" { & $VenvPython autostart.py on }
} finally { Pop-Location }

Say "Starting M.I.N.D..."
Start-Process -FilePath (Join-Path $Venv "Scripts\pythonw.exe") -ArgumentList "main.py" -WorkingDirectory $Backend

Write-Host ""
Write-Host "Done! M.I.N.D is starting. Its setup screen opens in a moment (name, free keys, your voice)." -ForegroundColor Green
Write-Host "To pin it to the taskbar: Start menu, type MIND, right-click it, Pin to taskbar." -ForegroundColor Green
Stop-Transcript | Out-Null
