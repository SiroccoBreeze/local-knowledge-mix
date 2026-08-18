"""Phase-1 static configuration.

Policy: plain values only — no config framework, no dynamic reload.
All values are import-time constants, overridable via env vars (LK_*) or by
tests that replace `app.config.settings`.
"""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Well-known names never treated as documents; hidden entries are ignored too.
IGNORED_NAMES = frozenset(
    {
        ".git",
        ".obsidian",
        ".trash",
        ".idea",
        ".vscode",
        "node_modules",
        "__pycache__",
        ".venv",
    }
)


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


@dataclass
class Settings:
    """Single source of truth for runtime paths and limits.

    raw_root is the *only* read-only asset directory in phase 1. Everything the
    system writes is derived: db_path (SQLite) and whatever SQLAlchemy creates.
    """

    raw_root: Path = _env_path("LK_RAW_ROOT", REPO_ROOT / "raw")
    db_path: Path = _env_path("LK_DB_PATH", REPO_ROOT / "data" / "knowledge.db")
    host: str = os.environ.get("LK_HOST", "127.0.0.1")
    port: int = int(os.environ.get("LK_PORT", "8000"))
    extensions: tuple[str, ...] = (".md",)
    # Files larger than this are skipped (recorded as failed) — protects the
    # reader from accidental binary pickles etc.
    max_file_bytes: int = 5 * 1024 * 1024
    schema_version: int = 1

    def resolve(self) -> "Settings":
        return Settings(
            raw_root=self.raw_root.resolve(),
            db_path=self.db_path.resolve(),
            host=self.host,
            port=self.port,
            extensions=self.extensions,
            max_file_bytes=self.max_file_bytes,
            schema_version=self.schema_version,
        )


settings = Settings()


def get_settings() -> Settings:
    """Live accessor.

    Consumer modules must read configuration through this function (or through
    ``app.config.settings`` at call time), NOT ``from app.config import
    settings`` — an import binds the object once, so tests that swap the
    module attribute would be invisible to everyone who already imported.
    """
    return settings
