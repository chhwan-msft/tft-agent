from pathlib import Path
from dotenv import load_dotenv, find_dotenv


def load_nearest_dotenv(start_path: str | Path = None, override: bool = False) -> Path | None:
    """Search for a .env file starting at start_path (or caller file dir) and walk up to filesystem root.

    If found, load it with python-dotenv. Returns the Path loaded or None.
    By default does not override existing environment variables unless override=True.
    """
    p = Path(start_path) if start_path else Path.cwd()
    if p.is_file():
        p = p.parent

    root = p.anchor
    while True:
        env_path = p / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=override)
            return env_path
        if str(p) == root:
            break
        p = p.parent

    # Fallback to find_dotenv (looks from CWD upward)
    found = find_dotenv()
    if found:
        load_dotenv(dotenv_path=found, override=override)
        return Path(found)

    return None
