import json
from pathlib import Path

import pytest
from app.config import settings
from app.main import app, get_bundle_file
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

BUNDLE_URL = "/api/v1/bundle"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def guarded_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tiny bundle with real files right outside its root, so a 404 proves the guard."""
    root = tmp_path / "v1"
    (root / "groups").mkdir(parents=True)
    (root / "manifest.json").write_text('{"kind": "manifest"}')
    (root / "groups" / "GROUP_T001.json").write_text('{"kind": "group"}')
    (root / "notes.txt").write_text("not part of the contract")
    (tmp_path / "secret.json").write_text('{"secret": true}')
    sibling = tmp_path / "v1-private"
    sibling.mkdir()
    (sibling / "secret.json").write_text('{"secret": true}')
    (root / "escape.json").symlink_to(tmp_path / "secret.json")
    (root / "escape").symlink_to(sibling, target_is_directory=True)
    monkeypatch.setattr(settings, "bundle_dir", root)
    return root


@pytest.mark.anyio
async def test_serves_the_manifest_of_the_fixture_bundle(fixture_bundle: Path) -> None:
    async with _client() as client:
        response = await client.get(f"{BUNDLE_URL}/manifest.json")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-cache"
    expected = json.loads((fixture_bundle / "manifest.json").read_text())
    assert response.json() == expected
    assert response.json()["schema"] == "xray-export-v1"


@pytest.mark.anyio
async def test_serves_every_fixture_file_byte_for_byte(fixture_bundle: Path) -> None:
    files = sorted(fixture_bundle.rglob("*.json"))
    assert any(path.parent.name == "groups" for path in files)

    async with _client() as client:
        for path in files:
            relative = path.relative_to(fixture_bundle).as_posix()
            response = await client.get(f"{BUNDLE_URL}/{relative}")
            assert response.status_code == 200, relative
            assert response.content == path.read_bytes(), relative


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "missing.json",
        "groups/GROUP_DOES_NOT_EXIST.json",
        "groups",
        "groups/",
        "",
    ],
)
async def test_unknown_bundle_paths_are_404(fixture_bundle: Path, path: str) -> None:
    async with _client() as client:
        response = await client.get(f"{BUNDLE_URL}/{path}")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_missing_bundle_directory_is_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "bundle_dir", tmp_path / "not-exported-yet")
    async with _client() as client:
        response = await client.get(f"{BUNDLE_URL}/manifest.json")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_only_json_files_are_served(guarded_bundle: Path) -> None:
    assert (guarded_bundle / "notes.txt").is_file()
    async with _client() as client:
        served = await client.get(f"{BUNDLE_URL}/groups/GROUP_T001.json")
        refused = await client.get(f"{BUNDLE_URL}/notes.txt")
    assert served.status_code == 200
    assert refused.status_code == 404


TRAVERSAL_PATHS = [
    "../secret.json",
    "groups/../../secret.json",
    "../v1-private/secret.json",
    "escape.json",
    "escape/secret.json",
]


@pytest.mark.parametrize("path", TRAVERSAL_PATHS)
def test_guard_refuses_paths_that_leave_the_bundle(guarded_bundle: Path, path: str) -> None:
    # Every one of these points at a real JSON file, so only the guard can refuse it.
    assert (guarded_bundle / path).resolve().is_file()
    with pytest.raises(HTTPException) as refused:
        get_bundle_file(path)
    assert refused.value.status_code == 404


def test_guard_refuses_absolute_paths(guarded_bundle: Path) -> None:
    outside = guarded_bundle.parent / "secret.json"
    with pytest.raises(HTTPException) as refused:
        get_bundle_file(str(outside))
    assert refused.value.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        *TRAVERSAL_PATHS,
        "..%2Fsecret.json",
        "groups%2F..%2F..%2Fsecret.json",
        "%2E%2E/secret.json",
        "..%2Fv1-private%2Fsecret.json",
    ],
)
async def test_traversal_over_http_never_leaks_a_file(guarded_bundle: Path, path: str) -> None:
    async with _client() as client:
        response = await client.get(f"{BUNDLE_URL}/{path}")
    assert response.status_code == 404
    assert "secret" not in response.text


@pytest.mark.anyio
async def test_absolute_path_over_http_is_404(guarded_bundle: Path) -> None:
    outside = guarded_bundle.parent / "secret.json"
    async with _client() as client:
        # '/api/v1/bundle/' + '/abs/path' -> the captured path is absolute.
        response = await client.get(f"{BUNDLE_URL}/{outside}")
    assert response.status_code == 404
    assert "secret" not in response.text
