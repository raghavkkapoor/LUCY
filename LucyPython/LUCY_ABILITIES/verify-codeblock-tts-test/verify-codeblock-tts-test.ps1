$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Speech
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer

$voice.Speak("Running the test again now.")

Write-Output "TEST_STARTED=True"
Write-Output "POWERSHELL_CODEBLOCK_ONLY=True"
Write-Output "TTS_WORKING=True"
Write-Output "READY_FOR_RESULT=True"
