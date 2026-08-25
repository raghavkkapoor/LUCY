import sys
import importlib.util
from pathlib import Path

ROOT = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython")
HANDLER = ROOT / "Services[IGNORE]" / "Emailing" / "Gmailhandler.py"

spec = importlib.util.spec_from_file_location("lucy_gmailhandler", str(HANDLER))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

creds = mod.run_new_oauth_flow()

if creds is None:
    print("OAUTH_SUCCESS=False")
    sys.exit(1)

print("OAUTH_SUCCESS=True")
