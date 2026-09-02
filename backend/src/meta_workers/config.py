from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    openai_api_key: str
    default_model: str
    allowed_models: tuple[str, ...]
    sandbox_image: str
    artifact_ttl_days: int

    @property
    def database_path(self) -> Path:
        return self.data_dir / "meta-workers.sqlite3"

    @classmethod
    def from_env(cls) -> "Settings":
        default_model = os.getenv("OPENAI_MODEL", "gpt-5.6")
        allowed = tuple(
            item.strip()
            for item in os.getenv("OPENAI_MODEL_ALLOWLIST", "gpt-5.6").split(",")
            if item.strip()
        )
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", "data")).resolve(),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            default_model=default_model,
            allowed_models=allowed,
            sandbox_image=os.getenv("SANDBOX_IMAGE", "meta-workers-sandbox:local"),
            artifact_ttl_days=int(os.getenv("ARTIFACT_TTL_DAYS", "30")),
        )
