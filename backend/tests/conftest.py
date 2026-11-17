"""Set test isolation before collection imports any cached application settings."""
import os
from pathlib import Path

os.environ["KUSYS_DATABASE_URL"] = "sqlite+pysqlite:////tmp/kusys_pytest_full_flow.db"
os.environ["KUSYS_STORAGE_PATH"] = "/tmp/kusys_pytest_artifacts"
os.environ["KUSYS_INLINE_JOBS"] = "true"
os.environ["KUSYS_SECURE_COOKIES"] = "false"
# Each test container is disposable. Remove a prior file before engine creation.
Path("/tmp/kusys_pytest_full_flow.db").unlink(missing_ok=True)
