# scrcpy_device/_utils.py
import os
from ._config import ScrcpyConfig

def find_server_jar(config: ScrcpyConfig) -> str:
    """Locate the scrcpy server jar file."""
    jar_name = config.jar_filename or f"scrcpy-server-v{config.server_version}"
    # Search in package directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, jar_name),
        os.path.join(os.getcwd(), jar_name),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"Server jar not found. Searched: {candidates}. "
        "Please download the scrcpy server jar and place it alongside the library."
    )