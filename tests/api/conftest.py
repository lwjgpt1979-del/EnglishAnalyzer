import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend/ so os.getenv() picks up ASYNC_DATABASE_URL
# before any app module (e.g. database.py) is imported at collection time.
_env_file = Path(__file__).parent.parent.parent / "backend" / ".env"
load_dotenv(_env_file, override=False)
