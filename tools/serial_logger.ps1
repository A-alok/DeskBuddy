param(
  [string]$PortName = "COM5",
  [int]$Seconds = 300,
  [string]$OutFile = "voice_capture.log"
)

# Passive serial logger: opens the port WITHOUT asserting DTR/RTS (so it does not
# reboot the CH343-connected ESP32), streams everything to a file with timestamps.
# Run it, then issue voice commands at your own pace; read the file afterward.

$port = New-Object System.IO.Ports.SerialPort $PortName,115200,None,8,one
$port.DtrEnable = $false
$port.RtsEnable = $false
try {
  $port.Open()
  $writer = [System.IO.StreamWriter]::new($OutFile, $false)
  $writer.AutoFlush = $true
  $end = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $end) {
    if ($port.BytesToRead -gt 0) {
      $chunk = $port.ReadExisting()
      $writer.Write($chunk)
      Write-Host -NoNewline $chunk
    }
    Start-Sleep -Milliseconds 80
  }
  $writer.Close()
}
finally {
  $port.Close()
}
