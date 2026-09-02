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
        openai_api_key="",
        default_model="gpt-5.6",
        allowed_models=("gpt-5.6",),
        sandbox_image="meta-workers-sandbox:test",
        artifact_ttl_days=30,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
