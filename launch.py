"""Expose wheel-provided CUDA libraries before Python loads CTranslate2."""
import os
import site
import sys
from pathlib import Path


def main():
    libraries = []
    for folder in site.getsitepackages():
        libraries.extend(str(path) for path in sorted((Path(folder) / "nvidia").glob("*/lib")))
    env = os.environ.copy()
    if libraries:
        env["LD_LIBRARY_PATH"] = os.pathsep.join(libraries + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []))
    command = sys.argv[1:] or ["-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1"]
    os.execve(sys.executable, [sys.executable, *command], env)


if __name__ == "__main__":
    main()
