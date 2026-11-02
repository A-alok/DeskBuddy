param(
  [string]$PortName = "COM5",
  [int]$Seconds = 25,
  [switch]$Reset
)

$port = New-Object System.IO.Ports.SerialPort $PortName,115200,None,8,one
try {
  $port.Open()
  if ($Reset) {
    # Pulse RTS to hard-reset the board so we see the boot log from the top.
    $port.DtrEnable = $false; $port.RtsEnable = $true
    Start-Sleep -Milliseconds 150
    $port.RtsEnable = $false
    Start-Sleep -Milliseconds 150
  } else {
    # Listen WITHOUT disturbing the board. On the CH343, DTR/RTS are wired to
    # EN/BOOT, so asserting them reboots the ESP32 — which would restart the
    # device in the middle of whatever command you are trying to capture. Keep
    # both lines de-asserted so opening the port is passive.
    $port.DtrEnable = $false; $port.RtsEnable = $false
  }

  $total = 0
  $end = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $end) {
    if ($port.BytesToRead -gt 0) {
      $chunk = $port.ReadExisting()
      Write-Host -NoNewline $chunk
      $total += $chunk.Length
    }
    Start-Sleep -Milliseconds 80
  }
  Write-Host ""
  Write-Host "--- captured $total bytes from $PortName ---"
}
finally {
  $port.Close()
}
