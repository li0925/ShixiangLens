$ErrorActionPreference = 'Stop'
$destination = Join-Path $PSScriptRoot 'wheels'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$packages = @{
    'PyQt5'='5.15.11'; 'PyQt5-Qt5'='5.15.2'; 'PyQt5-sip'='12.15.0'
    'rapidocr'='3.10.0'; 'numpy'='1.26.4'; 'onnxruntime'='1.19.2'
    'opencv-python-headless'='4.10.0.84'; 'pyclipper'='1.3.0.post6'; 'shapely'='2.0.6'
    'PyYAML'='6.0.2'; 'Pillow'='11.3.0'; 'six'='1.17.0'; 'coloredlogs'='15.0.1'
    'flatbuffers'='25.2.10'; 'packaging'='25.0'; 'protobuf'='5.29.5'; 'sympy'='1.13.3'
    'humanfriendly'='10.0'; 'mpmath'='1.3.0'; 'pyinstaller'='6.16.0'
    'altgraph'='0.17.4'; 'pyinstaller-hooks-contrib'='2025.8'; 'pefile'='2023.2.7'
    'importlib-metadata'='8.7.0'; 'zipp'='3.23.0'; 'tqdm'='4.67.1'; 'colorama'='0.4.6'
    'pywin32-ctypes'='0.2.3'; 'setuptools'='80.9.0'; 'pyreadline3'='3.5.4'
}
foreach ($name in $packages.Keys) {
    $version = $packages[$name]
    $metadata = Invoke-RestMethod "https://pypi.org/pypi/$name/$version/json"
    $candidates = @($metadata.urls | Where-Object {
        $_.packagetype -eq 'bdist_wheel' -and (
          $_.filename -match '(cp39-cp39|cp39-abi3|cp38-abi3|cp37-abi3|cp36-abi3|py3-none)-win_amd64.whl$' -or
          $_.filename -match '(py3|py2.py3)-none-any.whl$'
        )
    })
    if (!$candidates.Count) { throw "No compatible wheel for $name" }
    $wheel = $candidates[0]
    $target = Join-Path $destination $wheel.filename
    if (!(Test-Path -LiteralPath $target)) {
        Invoke-WebRequest -Uri $wheel.url -OutFile $target
    }
    $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $wheel.digests.sha256) { throw "Hash mismatch: $target" }
    Write-Output "$name $version verified"
}
