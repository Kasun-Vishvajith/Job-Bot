$filePath = Join-Path $PSScriptRoot "index.html"
$all = Get-Content $filePath -Encoding UTF8
# Keep lines 0..650 (0-indexed) and 1873..end
$out = $all[0..650] + $all[1873..($all.Length - 1)]
Set-Content -Path $filePath -Value $out -Encoding UTF8
Write-Host "Done. New line count: $($out.Length)"
