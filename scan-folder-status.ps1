param(
    [string]$RootPath = (Get-Location).Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FolderSignals {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FolderPath,
        [Parameter(Mandatory = $true)]
        [string[]]$CodeExtensions,
        [Parameter(Mandatory = $true)]
        [string[]]$AssetExtensions
    )

    $hasGit = $false
    $hasAnyFile = $false
    $hasCode = $false
    $hasAssets = $false

    $stack = [System.Collections.Generic.Stack[string]]::new()
    $stack.Push($FolderPath)

    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        $children = @()

        try {
            $children = Get-ChildItem -LiteralPath $current -Force -ErrorAction Stop
        } catch {
            # Skip unreadable directories and continue scanning.
            continue
        }

        foreach ($child in $children) {
            if ($child.Name -eq ".git") {
                $hasGit = $true
            }

            if ($child.PSIsContainer) {
                $stack.Push($child.FullName)
                continue
            }

            $hasAnyFile = $true
            $ext = [System.IO.Path]::GetExtension($child.Name).ToLowerInvariant()

            if ($CodeExtensions -contains $ext) {
                $hasCode = $true
            }

            if ($AssetExtensions -contains $ext) {
                $hasAssets = $true
            }
        }
    }

    [pscustomobject]@{
        HasGit = $hasGit
        HasCode = $hasCode
        HasAssets = $hasAssets
        IsEmpty = -not $hasAnyFile
    }
}

function Write-Marker {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$On,
        [Parameter(Mandatory = $true)]
        [string]$OnText,
        [Parameter(Mandatory = $true)]
        [string]$OffText,
        [Parameter(Mandatory = $true)]
        [string]$OnColor
    )

    $display = if ($On) { $OnText } else { $OffText }
    $color = if ($On) { $OnColor } else { "DarkGray" }
    Write-Host ("{0,-10}" -f $display) -NoNewline -ForegroundColor $color
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path

$codeExtensions = @(
    ".ps1", ".psm1", ".psd1",
    ".py", ".ipynb",
    ".js", ".jsx", ".ts", ".tsx",
    ".java", ".kt", ".kts", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc",
    ".cs", ".go", ".rs",
    ".rb", ".php", ".swift", ".m",
    ".sh", ".bash", ".zsh",
    ".html", ".css", ".scss", ".sass",
    ".sql", ".r", ".dart", ".lua"
)

$assetExtensions = @(
    ".png", ".jpg", ".jpeg", ".gif", ".bmp",
    ".webp", ".svg", ".ico", ".tif", ".tiff", ".avif"
)

$folders = Get-ChildItem -LiteralPath $resolvedRoot -Directory -Force | Sort-Object Name

if ($folders.Count -eq 0) {
    Write-Host "No child folders found in $resolvedRoot" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host ("Root: {0}" -f $resolvedRoot) -ForegroundColor Cyan
Write-Host ("{0,-52}{1,-10}{2,-10}{3,-10}{4,-10}" -f "Folder", "GitTree", "Code", "Assets", "Empty") -ForegroundColor White
Write-Host ("{0}" -f ("-" * 92)) -ForegroundColor DarkGray

foreach ($folder in $folders) {
    $signals = Get-FolderSignals -FolderPath $folder.FullName -CodeExtensions $codeExtensions -AssetExtensions $assetExtensions
    $codeNoGit = (-not $signals.HasGit) -and $signals.HasCode

    Write-Host ("{0,-52}" -f $folder.Name) -NoNewline -ForegroundColor White
    Write-Marker -On $signals.HasGit -OnText "[GIT]" -OffText "[    ]" -OnColor "Green"
    Write-Marker -On $codeNoGit -OnText "[CODE]" -OffText "[    ]" -OnColor "Cyan"
    Write-Marker -On $signals.HasAssets -OnText "[ASSET]" -OffText "[     ]" -OnColor "Magenta"
    Write-Marker -On $signals.IsEmpty -OnText "[EMPTY]" -OffText "[     ]" -OnColor "Yellow"
    Write-Host ""
}

Write-Host ""
Write-Host "Legend:" -ForegroundColor White
Write-Host "  [GIT]   folder is a git repo or contains one" -ForegroundColor Green
Write-Host "  [CODE]  contains code files but no git repo in tree" -ForegroundColor Cyan
Write-Host "  [ASSET] contains image-like assets in tree" -ForegroundColor Magenta
Write-Host "  [EMPTY] no files anywhere in tree (only empty folders or nothing)" -ForegroundColor Yellow
