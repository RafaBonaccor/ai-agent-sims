$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceDir = Join-Path $projectRoot "java\src\blockforge"
$outputDir = Join-Path $projectRoot "java\out"

Write-Host "Blockforge Java" -ForegroundColor Cyan
Write-Host "Cartella progetto: $projectRoot"

$javac = Get-Command javac -ErrorAction SilentlyContinue
$java = Get-Command java -ErrorAction SilentlyContinue

if (-not $javac -or -not $java) {
    $correttoHome = "C:\Program Files\Amazon Corretto\jdk21.0.6_7\bin"
    $javacPath = Join-Path $correttoHome "javac.exe"
    $javaPath = Join-Path $correttoHome "java.exe"

    if ((Test-Path $javacPath) -and (Test-Path $javaPath)) {
        $javac = @{ Source = $javacPath }
        $java = @{ Source = $javaPath }
    } else {
        throw "Java 21 non trovato. Installa Java oppure aggiungi javac/java al PATH."
    }
}

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

$sourceFiles = Get-ChildItem -Path $sourceDir -Filter "*.java" | ForEach-Object { $_.FullName }
if ($sourceFiles.Count -eq 0) {
    throw "Nessun file sorgente Java trovato in $sourceDir"
}

Write-Host "Compilo i sorgenti Java..." -ForegroundColor Yellow
& $javac.Source -d $outputDir $sourceFiles
if ($LASTEXITCODE -ne 0) {
    throw "Compilazione Java fallita."
}

Write-Host "Compilazione completata." -ForegroundColor Green
Write-Host "Avvio la finestra del gioco..." -ForegroundColor Yellow
& $java.Source -cp $outputDir blockforge.Main
