
import time
import json
import subprocess
from pathlib import Path

results = []

def run_test(name, fn):
    try:
        result = fn()
        results.append({
            "test": name,
            "status": "PASS",
            "detail": str(result)[:100]
        })
    except Exception as e:
        results.append({
            "test": name,
            "status": "CAUGHT",
            "error": str(e)[:100]
        })

run_test(
    "exception_recovery",
    lambda: (_ for _ in ()).throw(Exception("simulated crash"))
)

run_test(
    "missing_file",
    lambda: Path("missing.txt").read_text()
)

run_test(
    "bad_json",
    lambda: json.loads("{bad}")
)

run_test(
    "unicode_output",
    lambda: "Lucy unicode test passed"
)

run_test(
    "child_process_failure",
    lambda: subprocess.run(
        ["python", "-c", "raise Exception('child failed')"],
        check=True,
        capture_output=True,
        text=True
    )
)

run_test(
    "short_timeout",
    lambda: time.sleep(0.1)
)

print(json.dumps({
    "isolated_test_run": True,
    "completed": len(results),
    "results": results
}, ensure_ascii=False))
