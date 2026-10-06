$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Test-Python311 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string[]]$PrefixArguments = @()
    )

    & $Command @PrefixArguments -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" *> $null
    return $LASTEXITCODE -eq 0
}

Push-Location -LiteralPath $PSScriptRoot
try {
    $bootstrapCommand = $null
    $bootstrapArguments = @()

    if ((Get-Command py -ErrorAction SilentlyContinue) -and
        (Test-Python311 -Command "py" -PrefixArguments @("-3.11"))) {
        $bootstrapCommand = "py"
        $bootstrapArguments = @("-3.11")
    }
    elseif ((Get-Command python -ErrorAction SilentlyContinue) -and
        (Test-Python311 -Command "python")) {
        $bootstrapCommand = "python"
    }

    if (-not $bootstrapCommand) {
        Write-Host "[Ari] Python 3.11 was not found."
        Write-Host "[Ari] Please install Python 3.11 and activate the py launcher or PATH."
        $exitCode = 1
    }
    else {
        Write-Host "[Ari] Installing project dependencies..."
        & $bootstrapCommand @bootstrapArguments "install_dependencies.py" @args
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            Write-Host "[Ari] Installation completed successfully."
        }
        else {
            Write-Host "[Ari] Installation failed. Please check the output above."
        }
    }
}
finally {
    Pop-Location
}

[void](Read-Host "Press Enter to continue...")
exit $exitCode
