<#
fw.ps1 – Biên dịch / nạp / kiểm thử firmware TV1 từ dòng lệnh (không cần mở Arduino IDE).

  .\fw.ps1 build                     biên dịch firmware chính (bật mọi cảnh báo)
  .\fw.ps1 build -Sketch hw          biên dịch sketch thử phần cứng
  .\fw.ps1 upload [-Port COM5]       biên dịch + nạp firmware chính (tự tìm cổng nếu chỉ có 1 ESP32)
  .\fw.ps1 upload -Sketch hw         nạp sketch thử phần cứng
  .\fw.ps1 test                      chạy kiểm thử logic cảnh báo trên máy tính (g++)
  .\fw.ps1 ports                     liệt kê cổng COM / board đang cắm
  .\fw.ps1 log [-Seconds 30] [-Send show,"set t_on 25"] [-Reset]   đọc log Serial (tools/serial_log.py)

Nạp lỗi "Connecting..." quá lâu: giữ nút BOOT; hoặc thêm -Slow để nạp ở 115200 baud.
Đóng Serial Monitor của Arduino IDE trước khi upload/log (một cổng COM chỉ mở được một nơi).
#>
param(
  [Parameter(Position = 0, Mandatory = $true)]
  [ValidateSet('build', 'upload', 'test', 'ports', 'log')]
  [string]$Action,
  [ValidateSet('main', 'hw')][string]$Sketch = 'main',
  [string]$Port,
  [double]$Seconds = 20,
  [string[]]$Send = @(),
  [switch]$Reset,
  [switch]$Slow
)
$ErrorActionPreference = 'Stop'
$fw = Split-Path -Parent $PSScriptRoot           # thư mục firmware/
$fqbn = 'esp32:esp32:esp32'                       # ESP32 Dev Module
$sketchDir = if ($Sketch -eq 'hw') { Join-Path $fw 'tv1_test_phan_cung' } else { Join-Path $fw 'tv1_firmware' }

function Get-Cli {
  $c = Get-Command arduino-cli -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  $bundled = Join-Path $env:LOCALAPPDATA 'Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe'
  if (Test-Path $bundled) { return $bundled }
  throw 'Khong thay arduino-cli (cai Arduino IDE 2.x hoac arduino-cli).'
}

function Get-EspPort {
  if ($Port) { return $Port }
  $found = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match '(CP210|CH340|CH910|USB-SERIAL|USB Serial|USB JTAG).*\((COM\d+)\)' } |
      ForEach-Object { [regex]::Match($_.Name, 'COM\d+').Value })
  if ($found.Count -eq 1) { return $found[0] }
  if ($found.Count -eq 0) { throw 'Khong thay ESP32: cam USB (cap co truyen du lieu), kiem tra driver CP210x/CH340, hoac dung -Port COMx.' }
  throw "Co nhieu cong: $($found -join ', '). Dung -Port COMx."
}

function Assert-Secrets {
  if ($Sketch -eq 'main' -and -not (Test-Path (Join-Path $sketchDir 'secrets.h'))) {
    throw 'Chua co tv1_firmware/secrets.h: copy secrets.example.h thanh secrets.h roi dien Wi-Fi va IP laptop.'
  }
}

switch ($Action) {
  'build' {
    Assert-Secrets
    & (Get-Cli) compile --fqbn $fqbn --warnings all $sketchDir
    exit $LASTEXITCODE
  }
  'upload' {
    Assert-Secrets
    $p = Get-EspPort
    $opts = @()
    if ($Slow) { $opts = @('--board-options', 'UploadSpeed=115200') }
    Write-Host "Nap $Sketch vao $p ..."
    & (Get-Cli) compile --fqbn $fqbn --warnings all @opts --upload --port $p $sketchDir
    exit $LASTEXITCODE
  }
  'test' {
    $gpp = Get-Command g++ -ErrorAction SilentlyContinue
    if (-not $gpp) {
      $gpp = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\BrechtSanders.WinLibs*\mingw64\bin\g++.exe') -ErrorAction SilentlyContinue | Select-Object -First 1
      if (-not $gpp) { throw 'Khong thay g++ (winget install BrechtSanders.WinLibs.POSIX.UCRT).' }
      $env:PATH = "$(Split-Path $gpp.FullName);$env:PATH"   # g++ cần thư mục bin của nó trong PATH
    }
    # ArduinoJson chỉ là thư viện header, dùng chung bản Arduino IDE đã cài cho kiểm thử JSON.
    $ajson = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Arduino\libraries\ArduinoJson\src'
    $suites = @(
      @{ name = 'canh bao'; src = @('test_alerts.cpp', '../tv1_firmware/alerts.cpp'); inc = @() },
      @{ name = 'BH1750';   src = @('test_light.cpp', '../tv1_firmware/light.cpp', '../tv1_firmware/alerts.cpp'); inc = @() },
      @{ name = 'JSON API'; src = @('test_payload.cpp', '../tv1_firmware/payload.cpp', '../tv1_firmware/alerts.cpp'); inc = @("-I$ajson") }
    )
    $failed = @()
    Push-Location (Join-Path $fw 'test_host')
    try {
      foreach ($s in $suites) {
        Write-Host "===== Kiem thu $($s.name) ====="
        $exe = Join-Path $env:TEMP ("tv1_test_" + ($s.src[0] -replace '\.cpp$', '') + '.exe')
        g++ -std=c++17 -Wall -Wextra -I../tv1_firmware @($s.inc) @($s.src) -o $exe
        if ($LASTEXITCODE -ne 0) { $failed += "$($s.name) (bien dich)"; continue }
        & $exe
        if ($LASTEXITCODE -ne 0) { $failed += $s.name }
      }
    } finally { Pop-Location }

    # Gói JSON firmware tạo ra -> backend thật của nhóm (backend/app). Cần Python + FastAPI.
    $backend = Join-Path (Split-Path -Parent $fw) 'backend\app\main.py'
    $payloadExe = Join-Path $env:TEMP 'tv1_test_test_payload.exe'
    python -c "import fastapi" 2>$null
    if ((Test-Path $backend) -and (Test-Path $payloadExe) -and $LASTEXITCODE -eq 0) {
      Write-Host '===== Kiem goi JSON bang backend cua nhom ====='
      $dumpDir = Join-Path $env:TEMP 'tv1_payloads'
      Remove-Item $dumpDir -Recurse -Force -ErrorAction SilentlyContinue
      New-Item -ItemType Directory $dumpDir | Out-Null
      & $payloadExe --dump $dumpDir | Out-Null
      $env:PYTHONWARNINGS = 'ignore'
      python (Join-Path $PSScriptRoot 'check_payloads.py') $dumpDir
      if ($LASTEXITCODE -ne 0) { $failed += 'JSON qua backend' }
    } else {
      Write-Host '(Bo qua kiem goi JSON bang backend: can repo co backend/ va pip install -r backend/requirements.txt)'
    }
    if ($failed.Count) { Write-Host "KHONG DAT: $($failed -join ', ')"; exit 1 }
    Write-Host 'TAT CA KIEM THU DAT'
    exit 0
  }
  'ports' {
    & (Get-Cli) board list
    Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match '\(COM\d+\)' } | Select-Object -ExpandProperty Name
  }
  'log' {
    $a = @((Join-Path $PSScriptRoot 'serial_log.py'), '-s', $Seconds)
    if ($Port) { $a += @('-p', $Port) }
    if ($Reset) { $a += '--reset' }
    foreach ($s in $Send) { $a += @('--send', $s) }
    python @a
    exit $LASTEXITCODE
  }
}
