import json
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.config import settings


@pytest.mark.anyio
async def test_execution_lifecycle_and_measurement_history(tmp_path, monkeypatch):
    # Isolated engine export: no writes to the developer's bundle or database.
    entity = f"COMP_{uuid4().int}"
    group = f"GROUP_{uuid4().int}"
    monkeypatch.setattr(settings, "bundle_dir", tmp_path)
    (tmp_path / "companies").mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"bundle_id": "one"}))
    path = tmp_path / "companies" / f"{entity}.json"
    doc = {"id": entity, "group_id": group, "months": [{"month": "2026-08", "shown": 690, "actions": [
        {"id": "debt-burden", "pillar": "debt", "title": "Bajar deuda", "unit": "%", "current": 3.1, "target": 2.17, "uplift_tenths": 8}]}],
        "series": [{"key": "debt_burden", "unit": "ratio", "values": [0.031]}]}
    path.write_text(json.dumps(doc))
    scope = {"entity_id": entity, "group_id": group, "kind": "company"}
    body = {**scope, "corte": "2026-08", "bundle_id": "one", "action_ids": ["debt-burden"], "actor": "CFO"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        url = "/api/v1/action-executions"
        assert (await c.post(url, json={**body, "action_ids": ["debt-burden", "unknown"]})).status_code == 422
        assert (await c.get(url, params=scope)).json() == []
        assert (await c.post(url, json={**body, "bundle_id": "stale"})).status_code == 409
        assert (await c.post(url, json={**body, "group_id": "GROUP_0"})).status_code == 404
        result = await c.post(url, json=body)
        assert result.status_code == 200, result.text
        row = result.json()[0]
        assert row["snapshot"]["baseline"] == 3.1
        assert row["snapshot"]["score_tenths"] == 690
        assert row["status"] == "en_curso"
        assert len(row["events"]) == 1
        again = (await c.post(url, json=body)).json()
        assert len(again) == 1 and len(again[0]["events"]) == 1
        assert (await c.get(url, params={**scope, "group_id": "GROUP_0"})).json() == []
        change = {"group_id": group, "status": "completada", "version": 1, "actor": "CFO", "note": "Renegociada"}
        assert (await c.patch(f"{url}/{row['id']}", json={**change, "group_id": "GROUP_0"})).status_code == 404
        saved = (await c.patch(f"{url}/{row['id']}", json=change)).json()
        assert saved["version"] == 2
        assert saved["events"][-1]["payload"]["previous_status"] == "en_curso"
        assert (await c.patch(f"{url}/{row['id']}", json=change)).status_code == 409
        # Manual completion must not manufacture financial observations.
        refreshed = (await c.post(url + "/refresh", json=scope)).json()[0]
        assert not [e for e in refreshed["events"] if e["kind"] == "measurement"]
        doc["months"].append({"month": "2026-09", "shown": 710, "actions": []})
        doc["series"][0]["values"].append(0.025)
        path.write_text(json.dumps(doc))
        manifest.write_text(json.dumps({"bundle_id": "two"}))
        measured = (await c.post(url + "/refresh", json=scope)).json()[0]
        observations = [e for e in measured["events"] if e["kind"] == "measurement"]
        assert len(observations) == 1 and observations[0]["payload"]["value"] == 2.5
        assert measured["snapshot"] == row["snapshot"]
        assert len((await c.post(url + "/refresh", json=scope)).json()[0]["events"]) == 3
        # A correction remains a new, attributable observation, never an overwrite.
        manifest.write_text(json.dumps({"bundle_id": "three"}))
        doc["series"][0]["values"][-1] = None
        path.write_text(json.dumps(doc))
        revised = (await c.post(url + "/refresh", json=scope)).json()[0]
        assert len(revised["events"]) == 4
        assert revised["events"][-1]["payload"]["value"] is None
        assert (await c.get(url, params=scope)).json()[0]["status"] == "completada"


@pytest.mark.anyio
async def test_financing_only_confirmation_keeps_banks(tmp_path, monkeypatch):
    entity = f"COMP_{uuid4().int}"
    group = f"GROUP_{uuid4().int}"
    monkeypatch.setattr(settings, "bundle_dir", tmp_path)
    (tmp_path / "companies").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps({"bundle_id": "fin"}))
    (tmp_path / "companies" / f"{entity}.json").write_text(json.dumps({"id": entity, "group_id": group, "months": [{"month": "2026-08", "shown": 400, "actions": [], "financing": [{"id": "confirming", "title": "Gestionar confirming", "kind": "confirming", "amount": 45000, "uplift_tenths": 30}]}], "series": []}))
    body = {"entity_id": entity, "group_id": group, "kind": "company", "corte": "2026-08", "bundle_id": "fin", "actor": "CFO", "action_ids": [], "financing": [{"entity_id": entity, "id": "confirming", "banks": ["Banco de prueba"]}]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.post("/api/v1/action-executions", json=body)
        assert res.status_code == 200, res.text
        snapshot = res.json()[0]["snapshot"]
        assert snapshot["financing"] is True
        assert snapshot["banks"] == ["Banco de prueba"]
        assert snapshot["amount"] == 45000
        assert snapshot["baseline"] is None
        assert len((await c.post("/api/v1/action-executions", json=body)).json()) == 1
        body["financing"][0]["id"] = "invented"
        assert (await c.post("/api/v1/action-executions", json=body)).status_code == 422


@pytest.mark.anyio
async def test_open_decision_is_not_started_twice_and_empty_updates_are_rejected(tmp_path, monkeypatch):
    entity = f"COMP_{uuid4().int}"
    group = f"GROUP_{uuid4().int}"
    monkeypatch.setattr(settings, "bundle_dir", tmp_path)
    (tmp_path / "companies").mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"bundle_id": "one"}))
    path = tmp_path / "companies" / f"{entity}.json"
    action = {"id": "debt-burden", "pillar": "debt", "title": "Bajar deuda", "unit": "%", "current": 3.1, "target": 2.17, "uplift_tenths": 8}
    doc = {"id": entity, "group_id": group, "months": [{"month": "2026-08", "shown": 690, "actions": [action]}], "series": []}
    path.write_text(json.dumps(doc))
    body = {"entity_id": entity, "group_id": group, "kind": "company", "corte": "2026-08", "bundle_id": "one", "action_ids": ["debt-burden"], "actor": "CFO"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        url = "/api/v1/action-executions"
        row = (await c.post(url, json=body)).json()[0]
        # The next closing proposes the same lever again: it is still the same open decision.
        doc["months"].append({"month": "2026-09", "shown": 700, "actions": [action]})
        path.write_text(json.dumps(doc))
        manifest.write_text(json.dumps({"bundle_id": "two"}))
        later = {**body, "corte": "2026-09", "bundle_id": "two"}
        assert len((await c.post(url, json=later)).json()) == 1
        change = {"group_id": group, "status": "en_curso", "version": 1, "actor": "CFO", "note": "  "}
        assert (await c.patch(f"{url}/{row['id']}", json=change)).status_code == 422
        paused = (await c.patch(f"{url}/{row['id']}", json={**change, "status": "pausada"})).json()
        assert paused["status"] == "pausada" and paused["version"] == 2
        assert len((await c.post(url, json=later)).json()) == 1
        assert (await c.patch(f"{url}/{row['id']}", json={**change, "status": "completada", "version": 2})).status_code == 200
        # Once closed, the lever can be taken up again from the new closing.
        assert len((await c.post(url, json=later)).json()) == 2
