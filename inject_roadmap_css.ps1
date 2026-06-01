$roadmapPath = Join-Path $PSScriptRoot "roadmap.html"
$cssPath = Join-Path $PSScriptRoot "style_roadmap.css"
$html = Get-Content $roadmapPath -Raw -Encoding UTF8
$css = Get-Content $cssPath -Raw -Encoding UTF8
$start = $html.IndexOf("<style>")
$end = $html.IndexOf("</style>") + 8
$newHtml = $html.Substring(0, $start) + "<style>`n" + $css + "`n  </style>" + $html.Substring($end)
Set-Content -Path $roadmapPath -Value $newHtml -Encoding UTF8
Write-Host "Done"
