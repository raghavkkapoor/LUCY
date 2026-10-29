import shutil, os, sys
def get_python_command():
    """
    Return a command that invokes a real Python interpreter.

    A PyInstaller executable cannot be treated as a normal Python
    interpreter with the -c argument.
    """

    # An explicitly configured interpreter takes priority.
    configured = os.environ.get("LUCY_PYTHON")

    if configured:
        if not os.path.isfile(configured):
            raise FileNotFoundError(
                f"LUCY_PYTHON does not point to a file: {configured}"
            )

        return [configured]

    # In a normal Python run, the current interpreter is appropriate.
    if not getattr(sys, "frozen", False):
        return [sys.executable]

    # In a packaged build, locate a separately installed Python.
    python_exe = shutil.which("python")

    if python_exe:
        return [python_exe]

    # Windows Python Launcher fallback.
    py_launcher = shutil.which("py")

    if py_launcher:
        return [py_launcher, "-3"]

    raise RuntimeError(
        "PYTHON INTERPRETER NOT FOUND!"
        "Ensure you have Python >= 3.11 installed OR set LUCY_PYTHON "
        "to the full path of python.exe."
    )