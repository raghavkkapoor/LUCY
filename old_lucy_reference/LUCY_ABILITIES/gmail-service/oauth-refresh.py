import importlib.util
from pathlib import Path

root = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython")
handler = root / "Services[IGNORE]" / "Emailing" / "Gmailhandler.py"

spec = importlib.util.spec_from_file_location("lucy_gmailhandler", str(handler))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

creds = mod.get_credentials()

if creds and creds.valid:
    print("GMAIL_AUTH_READY=True")
else:
    print("GMAIL_AUTH_READY=False")
