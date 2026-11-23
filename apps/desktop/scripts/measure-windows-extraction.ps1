param([Parameter(Mandatory=$true)][string]$Archive,[Parameter(Mandatory=$true)][string]$DriveRoot,[Parameter(Mandatory=$true)][string]$RecordDirectory,[string]$NsisCompiler)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$taskId = [Guid]::NewGuid().ToString('N')
$resolvedDrive = [IO.Path]::GetFullPath($DriveRoot)
if ($resolvedDrive -ne [IO.Path]::GetPathRoot($resolvedDrive)) { throw 'DriveRoot must be a drive root' }
$target = [IO.Path]::GetFullPath((Join-Path $resolvedDrive ('GeneLoop-install-check-' + $taskId)))
if ([IO.Path]::GetDirectoryName($target).TrimEnd('\') -ne $resolvedDrive.TrimEnd('\')) { throw 'Unexpected diagnostic target' }
if (Test-Path -LiteralPath $target) { throw 'Diagnostic target already exists' }
$records = [IO.Path]::GetFullPath($RecordDirectory)
New-Item -ItemType Directory -Path $records -Force | Out-Null
$temp = Join-Path ([IO.Path]::GetTempPath()) ('GeneLoop-install-check-' + $taskId)
New-Item -ItemType Directory -Path $temp | Out-Null
$copy = Join-Path $temp 'payload.zip'
$timer = [Diagnostics.Stopwatch]::StartNew()
$result = [ordered]@{scope='isolated exact payload extraction and deletion; no app registration, no existing install changes';model_requests=0;target_drive=$resolvedDrive;archive_bytes=(Get-Item -LiteralPath $Archive).Length}
try {
    $part = [Diagnostics.Stopwatch]::StartNew()
    Copy-Item -LiteralPath $Archive -Destination $copy
    $result.copy_payload_to_system_temp_seconds = $part.Elapsed.TotalSeconds
    $zip = [IO.Compression.ZipFile]::OpenRead($copy)
    try {
        $entries = @($zip.Entries | Where-Object { $_.Name -ne '' })
        $files = $entries.Count
        $bytes = [long]0
        foreach ($entry in $entries) { $bytes += $entry.Length }
    } finally { $zip.Dispose() }
    $hash = (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLowerInvariant()
    $constants = Join-Path $records 'PayloadBuild.cs'
    $exe = Join-Path $records 'extract-diagnostic.exe'
    Set-Content -LiteralPath $constants -Value ('static class PayloadBuild { public const string Sha256="' + $hash + '"; public const int Files=' + $files + '; public const long Bytes=' + $bytes + 'L; }')
    $compiler = Join-Path $env:SystemRoot 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    & $compiler /nologo /target:winexe /reference:System.IO.Compression.dll ('/out:' + $exe) (Join-Path $PSScriptRoot '../setup/ExtractPayload.cs') $constants
    if ($LASTEXITCODE -ne 0) { throw 'Extractor compilation failed' }
    $log = Join-Path $records 'extract-timing.jsonl'
    $diagnosticExe = $exe
    $diagnosticArgs = @(('"'+$copy+'"'),('"'+$target+'"'),('"'+$log+'"'))
    if ($NsisCompiler) {
        $diagnosticExe = Join-Path $records 'nsis-write-diagnostic.exe'
        $template = @'
Unicode true
RequestExecutionLevel user
SilentInstall silent
SetCompress off
OutFile "@OUT@"
Section
  System::Call 'kernel32::GetTickCount() i.r3'
  InitPluginsDir
  File /oname=$PLUGINSDIR\payload.zip "@ARCHIVE@"
  File /oname=$PLUGINSDIR\extract.exe "@EXTRACT@"
  System::Call 'kernel32::GetTickCount() i.r4'
  IntOp $4 $4 - $3
  FileOpen $0 "@LOG@" a
  FileWrite $0 '{"phase":"nsis_payload_released","elapsed_ms":$4}$\n'
  FileClose $0
  ExecWait '"$PLUGINSDIR\extract.exe" "$PLUGINSDIR\payload.zip" "@TARGET@" "@LOG@"' $1
  SetErrorLevel $1
SectionEnd
'@
        $source = $template.Replace('@OUT@',$diagnosticExe).Replace('@ARCHIVE@',$copy).Replace('@EXTRACT@',$exe).Replace('@LOG@',$log).Replace('@TARGET@',$target)
        $nsi = Join-Path $records 'write-diagnostic.nsi'
        [IO.File]::WriteAllText($nsi,$source,[Text.Encoding]::UTF8)
        & $NsisCompiler /V1 $nsi
        if ($LASTEXITCODE -ne 0) { throw 'NSIS diagnostic compilation failed' }
        $diagnosticArgs = @()
        $result.scope = 'isolated NSIS startup, embedded payload release, exact extraction and deletion; no app registration or existing install changes'
    }
    $part.Restart()
    $process = Start-Process -FilePath $diagnosticExe -ArgumentList $diagnosticArgs -WindowStyle Hidden -PassThru
    $process.WaitForExit()
    $result.extract_exit_code = $process.ExitCode
    $result.extract_seconds = $part.Elapsed.TotalSeconds
    $result.files = $files
    $result.unpacked_bytes = $bytes
    if ($process.ExitCode -ne 0) { throw 'Extractor failed' }
    $result.extracted_version = (Get-Item -LiteralPath (Join-Path $target 'GeneLoop Desktop.exe')).VersionInfo.FileVersion
} finally {
    $result.total_before_cleanup_seconds = $timer.Elapsed.TotalSeconds
    $part = [Diagnostics.Stopwatch]::StartNew()
    # Both targets were exclusively created above; verify absolute boundaries
    # again before native PowerShell cleanup. Never touch the user's install.
    if ([IO.Path]::GetDirectoryName($target).TrimEnd('\') -ne $resolvedDrive.TrimEnd('\') -or [IO.Path]::GetFileName($target) -ne ('GeneLoop-install-check-' + $taskId)) { throw 'Refusing cleanup' }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    $result.delete_extracted_seconds = $part.Elapsed.TotalSeconds
    if ([IO.Path]::GetDirectoryName($temp) -ne [IO.Path]::GetTempPath().TrimEnd('\') -or [IO.Path]::GetFileName($temp) -ne ('GeneLoop-install-check-' + $taskId)) { throw 'Refusing temp cleanup' }
    Remove-Item -LiteralPath $temp -Recurse -Force
    $result.total_seconds = $timer.Elapsed.TotalSeconds
    $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $records 'result.json') -Encoding UTF8
    $result | ConvertTo-Json
}
