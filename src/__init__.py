from pathlib import Path

from .utils.dotenv_loader import load_nearest_dotenv

# When `import src` (or `python -m src...`) happens, try to load the nearest .env
# starting from the package directory. Do not override existing environment variables.
__dotenv_loaded__ = load_nearest_dotenv(start_path=Path(__file__).parent, override=False)

__all__ = []
