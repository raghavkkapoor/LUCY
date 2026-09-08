import subprocess
import sys
from pathlib import Path

tester = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\dynamic-chrome-page-registry\test_dynamic_pages.py")

p = subprocess.run(
    [sys.executable, str(tester)],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    errors="replace",
)

print(f"TEST_EXIT_CODE={p.returncode}")

print("TEST_STDOUT_BEGIN")
print(p.stdout)
print("TEST_STDOUT_END")

print("TEST_STDERR_BEGIN")
print(p.stderr)
print("TEST_STDERR_END")

sys.exit(0)
