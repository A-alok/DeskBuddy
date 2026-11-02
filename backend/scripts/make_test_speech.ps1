# Temporary: generate test WAVs with Windows SAPI.
# Deliberately 16 kHz / 16-bit / mono — the exact format the INMP441 capture will
# produce, so the test exercises the real thing rather than a convenient one.

Add-Type -AssemblyName System.Speech

$phrases = @{
    'wx'    = "What is the weather today"
    'timer' = "Set a timer for ten minutes"
    'relay' = "Turn on the lamp"
    'chat'  = "Explain what an I2S bus is in one sentence"
}

$outDir = Join-Path $PSScriptRoot "fixtures"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, `
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, `
    [System.Speech.AudioFormat.AudioChannel]::Mono)

foreach ($key in $phrases.Keys) {
    $path = Join-Path $outDir "_speech_$key.wav"
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.Rate = -1
    $synth.SetOutputToWaveFile($path, $fmt)
    $synth.Speak($phrases[$key])
    $synth.Dispose()
    $size = (Get-Item $path).Length
    Write-Output ("{0,-6} {1,7} bytes  `"{2}`"" -f $key, $size, $phrases[$key])
}
