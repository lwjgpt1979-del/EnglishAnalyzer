import sys
from pathlib import Path
from dotenv import load_dotenv

# Load backend/.env into os.environ before any app module is imported.
# This is needed because database.py initialises _async_engine at module
# level using os.getenv("ASYNC_DATABASE_URL").
_env_file = Path(__file__).parent.parent / "backend" / ".env"
load_dotenv(_env_file, override=False)

# Ensure backend/ is on sys.path so both `app.*` and `scripts.*` are importable.
_backend_dir = str(Path(__file__).parent.parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
