from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from meta_workers.config import Settings
from meta_workers.main import create_app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        data_dir=tmp_path,
        model_base_url="https://example.invalid/v1",
        model_api_key="",
        default_model="grok-4.3",
        allowed_models=("grok-4.3",),
        sandbox_image="meta-workers-sandbox:test",
        artifact_ttl_days=30,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
