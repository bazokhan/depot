param(
    [string]$LeftRoot = "D:\OneDrive\projects",
    [string]$RightRoot = "D:\projects"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FolderMetrics {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FolderPath
    )

    $fileCount = 0L
    $folderCount = 0L
    $totalBytes = 0L

    $stack = [System.Collections.Generic.Stack[string]]::new()
    $stack.Push($FolderPath)

    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        $entries = @()

        try {
            $entries = Get-ChildItem -LiteralPath $current -Force -ErrorAction Stop
        } catch {
            # Skip unreadable directories.
            continue
        }

        foreach ($entry in $entries) {
            if ($entry.PSIsContainer) {
                # Skip reparse points to avoid recursion loops.
                if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    continue
                }

                $folderCount++
                $stack.Push($entry.FullName)
                continue
            }

            $fileCount++
            $totalBytes += [int64]$entry.Length
        }
    }

    [pscustomobject]@{
        SizeBytes   = $totalBytes
        FileCount   = $fileCount
        FolderCount = $folderCount
    }
}

function Format-Bytes {
    param([int64]$Bytes)

    if ($Bytes -lt 1KB) { return "$Bytes B" }
    if ($Bytes -lt 1MB) { return ("{0:N2} KB" -f ($Bytes / 1KB)) }
    if ($Bytes -lt 1GB) { return ("{0:N2} MB" -f ($Bytes / 1MB)) }
    return ("{0:N2} GB" -f ($Bytes / 1GB))
}

function Write-MatchCell {
    param([bool]$IsMatch)

    if ($IsMatch) {
        Write-Host ("{0,-9}" -f "[MATCH]") -NoNewline -ForegroundColor Green
    } else {
        Write-Host ("{0,-9}" -f "[DIFF]") -NoNewline -ForegroundColor Red
    }
}

function Write-PresenceCell {
    param([bool]$Exists, [string]$Label)

    if ($Exists) {
        Write-Host ("{0,-8}" -f $Label) -NoNewline -ForegroundColor Cyan
    } else {
        Write-Host ("{0,-8}" -f "-") -NoNewline -ForegroundColor DarkGray
    }
}

$leftResolved = (Resolve-Path -LiteralPath $LeftRoot).Path
$rightResolved = (Resolve-Path -LiteralPath $RightRoot).Path

$leftChildren = Get-ChildItem -LiteralPath $leftResolved -Directory -Force | Group-Object -Property Name -AsHashTable -AsString
$rightChildren = Get-ChildItem -LiteralPath $rightResolved -Directory -Force | Group-Object -Property Name -AsHashTable -AsString

$allNames = @($leftChildren.Keys + $rightChildren.Keys | Sort-Object -Unique)

if ($allNames.Count -eq 0) {
    Write-Host "No child folders found in either root." -ForegroundColor Yellow
    exit 0
}

$results = foreach ($name in $allNames) {
    $leftExists = $leftChildren.ContainsKey($name)
    $rightExists = $rightChildren.ContainsKey($name)

    $leftMetrics = $null
    $rightMetrics = $null
    $isMatch = $false

    if ($leftExists) {
        $leftMetrics = Get-FolderMetrics -FolderPath $leftChildren[$name][0].FullName
    }

    if ($rightExists) {
        $rightMetrics = Get-FolderMetrics -FolderPath $rightChildren[$name][0].FullName
    }

    if ($leftExists -and $rightExists) {
        $isMatch = (
            $leftMetrics.SizeBytes -eq $rightMetrics.SizeBytes -and
            $leftMetrics.FileCount -eq $rightMetrics.FileCount -and
            $leftMetrics.FolderCount -eq $rightMetrics.FolderCount
        )
    }

    [pscustomobject]@{
        Name            = $name
        LeftExists      = $leftExists
        RightExists     = $rightExists
        LeftSizeBytes   = if ($leftMetrics) { $leftMetrics.SizeBytes } else { $null }
        RightSizeBytes  = if ($rightMetrics) { $rightMetrics.SizeBytes } else { $null }
        LeftFileCount   = if ($leftMetrics) { $leftMetrics.FileCount } else { $null }
        RightFileCount  = if ($rightMetrics) { $rightMetrics.FileCount } else { $null }
        LeftFolderCount = if ($leftMetrics) { $leftMetrics.FolderCount } else { $null }
        RightFolderCount= if ($rightMetrics) { $rightMetrics.FolderCount } else { $null }
        IsMatch         = $isMatch
    }
}

Write-Host ""
Write-Host ("Left : {0}" -f $leftResolved) -ForegroundColor Cyan
Write-Host ("Right: {0}" -f $rightResolved) -ForegroundColor Cyan
Write-Host ("{0,-36}{1,-8}{2,-8}{3,12}{4,12}{5,9}{6,9}{7,9}{8,9}{9,-9}" -f "Folder", "Left", "Right", "L-Size", "R-Size", "L-Files", "R-Files", "L-Dirs", "R-Dirs", "Status") -ForegroundColor White
Write-Host ("{0}" -f ("-" * 122)) -ForegroundColor DarkGray

foreach ($row in $results) {
    Write-Host ("{0,-36}" -f $row.Name) -NoNewline -ForegroundColor White
    Write-PresenceCell -Exists $row.LeftExists -Label "YES"
    Write-PresenceCell -Exists $row.RightExists -Label "YES"

    $leftSizeText = if ($row.LeftExists) { Format-Bytes -Bytes $row.LeftSizeBytes } else { "-" }
    $rightSizeText = if ($row.RightExists) { Format-Bytes -Bytes $row.RightSizeBytes } else { "-" }
    $leftFilesText = if ($row.LeftExists) { "$($row.LeftFileCount)" } else { "-" }
    $rightFilesText = if ($row.RightExists) { "$($row.RightFileCount)" } else { "-" }
    $leftDirsText = if ($row.LeftExists) { "$($row.LeftFolderCount)" } else { "-" }
    $rightDirsText = if ($row.RightExists) { "$($row.RightFolderCount)" } else { "-" }

    Write-Host ("{0,12}{1,12}{2,9}{3,9}{4,9}{5,9}" -f $leftSizeText, $rightSizeText, $leftFilesText, $rightFilesText, $leftDirsText, $rightDirsText) -NoNewline -ForegroundColor Gray

    if (-not $row.LeftExists -or -not $row.RightExists) {
        Write-Host ("{0,-9}" -f "[MISSING]") -ForegroundColor Yellow
    } else {
        Write-MatchCell -IsMatch $row.IsMatch
        Write-Host ""
    }
}

$matching = @($results | Where-Object { $_.LeftExists -and $_.RightExists -and $_.IsMatch }).Count
$different = @($results | Where-Object { $_.LeftExists -and $_.RightExists -and -not $_.IsMatch }).Count
$missing = @($results | Where-Object { -not $_.LeftExists -or -not $_.RightExists }).Count

Write-Host ""
Write-Host ("Matches : {0}" -f $matching) -ForegroundColor Green
Write-Host ("Differs : {0}" -f $different) -ForegroundColor Red
Write-Host ("Missing : {0}" -f $missing) -ForegroundColor Yellow
Write-Host "Comparison ignores creation dates and compares only recursive size, file count, and folder count." -ForegroundColor DarkGray
