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
    $python = (Get-Command python.exe).Source
    $priorPath = $env:PATH
    try {
        # Restrict DLL discovery to this interpreter and Windows instead of unrelated tools on PATH.
        $env:PATH = "$(Split-Path $python);$env:SystemRoot\System32;$env:SystemRoot"
        & $python -m PyInstaller --noconfirm --clean packaging/windows.spec
        if ($LASTEXITCODE) { throw 'PyInstaller build failed.' }
    } finally {
        $env:PATH = $priorPath
    }

    $executable = Get-Item -LiteralPath 'dist/CMX Material Manager/CMX Material Manager.exe'
    foreach ($asset in 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'docs/USER_GUIDE.md', 'docs/BUILD.md', 'examples/demo.cmx') {
        $target = Join-Path $executable.DirectoryName $asset
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $asset -Destination $target -Force
    }
    $priorPlatform = $env:QT_QPA_PLATFORM
    try {
        $env:QT_QPA_PLATFORM = 'offscreen'
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
        $smoke = Start-Process -FilePath $executable.FullName -WorkingDirectory $executable.DirectoryName -ArgumentList '--smoke-test examples/demo.cmx' -PassThru -WindowStyle Hidden
    } finally {
        $env:QT_QPA_PLATFORM = $priorPlatform
        $env:PATH = $priorPath
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
