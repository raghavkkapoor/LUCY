param(
    [Parameter(Mandatory=$true)]
    [string]$SearchTerm,
    [string]$Extension,
    [string]$Path,
    [switch]$FoldersOnly,
    [switch]$FilesOnly
)

$ErrorActionPreference = 'Stop'

Write-Host "Searching for '$SearchTerm'..." -ForegroundColor Yellow

$whereClauses = @("System.FileName LIKE '%$SearchTerm%'")

if ($Extension) {
    $extClean = $Extension.TrimStart('.')
    $whereClauses += "System.FileExtension = '$extClean'"
    Write-Host "Filtering by extension: $extClean" -ForegroundColor Gray
}

if ($Path) {
    $resolvedPath = (Resolve-Path $Path).Path
    $whereClauses += "System.ItemFolderPathDisplay LIKE '$resolvedPath%'"
    Write-Host "Restricting to path: $resolvedPath" -ForegroundColor Gray
}

if ($FoldersOnly) {
    $whereClauses += "System.Kind = 'Folder'"
    Write-Host "Filter: Folders only" -ForegroundColor Gray
} elseif ($FilesOnly) {
    $whereClauses += "System.Kind <> 'Folder'"
    Write-Host "Filter: Files only" -ForegroundColor Gray
}

$whereString = $whereClauses -join " AND "
$query = "SELECT System.ItemPathDisplay FROM SYSTEMINDEX WHERE $whereString"

$connection = New-Object -ComObject ADODB.Connection
$recordset = New-Object -ComObject ADODB.Recordset

$connection.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
$recordset.Open($query, $connection)

$results = @()
while (-not $recordset.EOF) {
    $results += $recordset.Fields.Item("System.ItemPathDisplay").Value
    $recordset.MoveNext()
}

$recordset.Close()
$connection.Close()

Write-Host "Found $($results.Count) results." -ForegroundColor Green
foreach ($res in $results) {
    [PSCustomObject]@{ Path = $res }
}