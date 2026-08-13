param(
    [Parameter(Mandatory = $true)]
    [string]$ExecutablePath,

    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"
$resolvedExecutable = (Resolve-Path $ExecutablePath).Path
$previousDataRoot = $env:WB_APP_DATA
$smokeDataRoot = Join-Path ([IO.Path]::GetTempPath()) "WBPriceAnalyzerSmoke-$PID"
$process = $null

try {
    $env:WB_APP_DATA = $smokeDataRoot
    $process = Start-Process -FilePath $resolvedExecutable -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $windowTitle = ""

    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $process.Refresh()
        if ($process.HasExited) {
            throw "Приложение завершилось при запуске с кодом $($process.ExitCode)."
        }
        $windowTitle = $process.MainWindowTitle
        if ($windowTitle -match "Unhandled exception|Failed to execute script") {
            throw "PyInstaller показал окно ошибки: $windowTitle"
        }
        if ($windowTitle -like "WB Price Analyzer*") {
            Write-Host "Проверка запуска пройдена: $windowTitle"
            exit 0
        }
    }

    throw "За $TimeoutSeconds секунд главное окно не появилось. Текущее окно: '$windowTitle'."
}
finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $process.Id -Timeout 5 -ErrorAction SilentlyContinue
    }
    if ($null -eq $previousDataRoot) {
        Remove-Item Env:WB_APP_DATA -ErrorAction SilentlyContinue
    }
    else {
        $env:WB_APP_DATA = $previousDataRoot
    }
    Remove-Item $smokeDataRoot -Recurse -Force -ErrorAction SilentlyContinue
}
