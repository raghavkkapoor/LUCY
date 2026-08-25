Add-Type -AssemblyName System.Speech
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice.Speak("When a design problem feels impossible, reduce it to goal, constraints, invariants, data flow, ownership, interfaces, risky assumptions, prototype, failure testing, and refactoring. Architecture skill grows by making designs, breaking them, and learning recurring patterns.")
Write-Output "ARCHITECTURE_ADVICE_SPOKEN=True"
