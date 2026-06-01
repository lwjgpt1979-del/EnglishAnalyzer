from pathlib import Path
from dotenv import load_dotenv

# Load backend/.env into os.environ before any app module is imported.
# This is needed because database.py initialises _async_engine at module
# level using os.getenv("ASYNC_DATABASE_URL").
_env_file = Path(__file__).parent.parent / "backend" / ".env"
load_dotenv(_env_file, override=False)
