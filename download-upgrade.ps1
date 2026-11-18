$ErrorActionPreference = 'Stop'
$destination = Join-Path $PSScriptRoot 'wheels'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$packages = @{
    'rapidocr'='3.10.0'; 'opencv-python-headless'='4.10.0.84'; 'omegaconf'='2.3.0'
    'antlr4-python3-runtime'='4.9.3'; 'requests'='2.32.5'; 'colorlog'='6.10.1'
    'charset-normalizer'='3.4.4'; 'idna'='3.11'; 'urllib3'='2.5.0'
    'certifi'='2026.10.5'; 'wheel'='0.45.1'
}
foreach ($name in $packages.Keys) {
    $version = $packages[$name]
    if ($name -eq 'certifi') { $metadata = Invoke-RestMethod "https://pypi.org/pypi/$name/json" }
    else { $metadata = Invoke-RestMethod "https://pypi.org/pypi/$name/$version/json" }
    $candidates = @($metadata.urls | Where-Object {
        $_.packagetype -eq 'bdist_wheel' -and (
          $_.filename -match '(cp39-cp39|cp39-abi3|cp38-abi3|cp37-abi3|cp36-abi3|py3-none)-win_amd64.whl$' -or
          $_.filename -match '(py3|py2.py3)-none-any.whl$')
    })
    if (!$candidates.Count -and $name -eq 'antlr4-python3-runtime') {
        $candidates = @($metadata.urls | Where-Object { $_.packagetype -eq 'sdist' })
    }
    if (!$candidates.Count) { throw "No compatible distribution for $name" }
    $wheel = $candidates[0]
    $target = Join-Path $destination $wheel.filename
    if (!(Test-Path -LiteralPath $target)) { Invoke-WebRequest -Uri $wheel.url -OutFile $target }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower() -ne $wheel.digests.sha256) {
        throw "Hash mismatch: $target"
    }
    Write-Output "$($wheel.filename) verified"
}
