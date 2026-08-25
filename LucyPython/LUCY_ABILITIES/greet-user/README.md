# Greet User

Goal: Respond successfully to a simple greeting through Lucy's PowerShell execution loop.

## Method
A minimal PowerShell command writes a deterministic success marker to standard output so Lucy can verify execution reliably.

## Stability / Risk
Very low risk and highly stable. It uses only built-in PowerShell output and makes no system changes.

## Verification
Successful execution must output:

GREETING_SPOKEN=True
