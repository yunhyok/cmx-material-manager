$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    $compiler = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (-not $compiler) {
        $compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
        if (-not (Test-Path -LiteralPath $compiler)) { throw 'Add Inno Setup 6.3+ or 7 ISCC.exe to PATH.' }
    }

    python -c "import sys, sysconfig; assert sys.version_info[:2] == (3, 12) and sysconfig.get_platform() == 'win-amd64', 'Python 3.12 x64 required'"
    if ($LASTEXITCODE) { throw 'Unsupported build environment.' }
    python -m PyInstaller --noconfirm --clean packaging/windows.spec
    if ($LASTEXITCODE) { throw 'PyInstaller build failed.' }

    $executable = Get-Item -LiteralPath 'dist/CMX Material Manager/CMX Material Manager.exe'
    foreach ($asset in 'README.md', 'docs/USER_GUIDE.md', 'examples/demo.cmx') {
        $target = Join-Path $executable.DirectoryName $asset
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $asset -Destination $target -Force
    }
    $priorPlatform = $env:QT_QPA_PLATFORM
    try {
        $env:QT_QPA_PLATFORM = 'offscreen'
        $smoke = Start-Process -FilePath $executable.FullName -WorkingDirectory $executable.DirectoryName -ArgumentList '--smoke-test examples/demo.cmx' -PassThru -WindowStyle Hidden
    } finally {
        $env:QT_QPA_PLATFORM = $priorPlatform
    }
    if (-not $smoke.WaitForExit(30000)) {
        $smoke.Kill()
        throw 'Frozen executable did not close the smoke-test window.'
    }
    if ($smoke.ExitCode -ne 0) { throw "Frozen executable returned $($smoke.ExitCode)." }
    $version = $executable.VersionInfo.ProductVersion
    if (-not $version) { throw 'Missing product version in the executable.' }
    & $compiler "/DAppVersion=$version" 'packaging/installer.iss'
    if ($LASTEXITCODE) { throw 'Inno Setup build failed.' }
    Get-FileHash -Algorithm SHA256 -LiteralPath "dist/CMX-Material-Manager-$version-windows-x64-setup.exe"
} finally {
    Pop-Location
}
