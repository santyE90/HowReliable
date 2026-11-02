"""History-only demo availability without weakening the default frozen API startup."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from howreliable.api.app import create_app as frozen_app
from howreliable.api.service import ArtifactContractError
from howreliable.config.settings import Settings
from howreliable.demo.app import create_app
from howreliable.demo.index import build_index
from test_demo_history import TIME, record, source_file


def test_missing_model_keeps_history_and_assessments_available(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, [record()]), path, TIME)
    app = create_app(root=tmp_path, index_path=path)
    assert app.state.prediction_service is None
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    page = client.get("/api/demo/v1/vehicles").json()
    identity = page["items"][0]["id"]
    assert client.get(f"/api/demo/v1/vehicles/{identity}/history").status_code == 200
    result = client.post("/api/demo/v1/purchase-assessments", json={
        "make": "mazda", "model": "mazda3", "year": 2020,
    })
    assert result.status_code == 200
    assert result.json()["historical_evidence"]["unique_report_count"] == 1
    for url in ["/api/v1/model", "/api/v1/cohorts", f"/api/v1/cohorts/{identity}",
                f"/api/demo/v1/vehicles/{identity}/prediction"]:
        response = client.get(url)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "MODEL_UNAVAILABLE"
    assert client.get("/api/demo/v1/nlp/sample-summary").status_code == 503


def test_original_api_still_fails_closed_by_default(tmp_path: Path) -> None:
    with pytest.raises(ArtifactContractError):
        frozen_app(root=tmp_path, settings=Settings(artifact_backend="local"))


def test_invalid_bundle_never_substitutes_a_model(tmp_path: Path) -> None:
    # An invalid manifest must go through the existing checksum-first loader, never deserialize.
    directory = tmp_path / "artifacts/registry/bundles/howreliable-rf-2022-cutoff-v1"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text('{"invalid":"not a model"}', encoding="utf-8")
    (directory / "manifest.sha256").write_text("0" * 64 + "\n", encoding="utf-8")
    with pytest.raises(ArtifactContractError):
        frozen_app(root=tmp_path, settings=Settings(artifact_backend="local"))
    app = frozen_app(root=tmp_path, settings=Settings(artifact_backend="local"),
                     allow_model_unavailable=True)
    assert app.state.prediction_service is None
    assert TestClient(app).get("/api/v1/model").status_code == 503
