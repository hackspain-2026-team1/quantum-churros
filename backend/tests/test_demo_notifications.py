import json
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Self
from urllib.request import Request

import app.demo_notifications as notifications


def alert(
    *,
    entity_id: str,
    month: str,
    kind: str,
    state: str = "fired",
) -> dict[str, Any]:
    suppressed = (
        None
        if state == "fired"
        else {"reason": "perimeter_change", "since": month, "until": month}
    )
    return {
        "id": f"{entity_id}:{month}:{kind}",
        "entity_kind": "company",
        "entity_id": entity_id,
        "group_id": "GROUP_TEST",
        "month": month,
        "kind": kind,
        "state": state,
        "title": {
            "deterioration_structural": "Deterioro estructural",
            "improvement_structural": "Mejora estructural",
            "level_critical": "Nivel crítico",
            "cap_fired": "Tope aplicado",
            "stale_feed": "Feed bancario sin datos",
        }[kind],
        "detail": "La señal se mantiene frente a 2026-02.",
        "shown": 669,
        "suppressed_by": suppressed,
    }


def write_bundle(root: Path, rows: list[dict[str, Any]]) -> None:
    root.mkdir(exist_ok=True)
    (root / "alerts.json").write_text(
        json.dumps({"schema": "xray-export-v1", "kind": "alerts", "alerts": rows}),
        encoding="utf-8",
    )


def write_entity(
    root: Path,
    *,
    entity_id: str = "COMP_TEST",
    month: str = "2026-08",
    actions: list[dict[str, Any]] | None = None,
) -> None:
    companies = root / "companies"
    companies.mkdir(exist_ok=True)
    action_rows = actions or []
    payload = {
        "id": entity_id,
        "months": [
            {
                "month": month,
                "shown": 669,
                "band": "stable",
                "conf": {"label": "medium"},
                "verdict": {
                    "direction": "deteriorating",
                    "persistence_months": 2,
                },
                "pillars": [
                    {
                        "key": "liquidity",
                        "score": 410,
                        "contrib": -120,
                        "note": "El colchón de liquidez se ha reducido.",
                    },
                    {
                        "key": "activity",
                        "score": 780,
                        "contrib": 64,
                        "note": "Los cobros todavía cubren los pagos.",
                    },
                    {
                        "key": "debt",
                        "score": 590,
                        "contrib": -20,
                        "note": "La carga financiera ha subido.",
                    },
                ],
                "actions": action_rows,
                "actions_combined": (
                    {"new_score": 754, "uplift": 85} if action_rows else None
                ),
            }
        ],
    }
    (companies / f"{entity_id}.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_load_fired_alerts_uses_latest_fired_close(tmp_path: Path) -> None:
    write_bundle(
        tmp_path,
        [
            alert(entity_id="COMP_OLD", month="2026-07", kind="level_critical"),
            alert(
                entity_id="COMP_NEW", month="2026-08", kind="deterioration_structural"
            ),
            alert(
                entity_id="COMP_MUTED",
                month="2026-09",
                kind="improvement_structural",
                state="suppressed",
            ),
        ],
    )

    month, rows = notifications.load_fired_alerts(tmp_path)

    assert month == "2026-08"
    assert [row["entity_id"] for row in rows] == ["COMP_NEW"]


def test_build_demo_emails_separates_internal_and_company_copy(
    tmp_path: Path,
) -> None:
    deterioration = alert(
        entity_id="COMP_TEST",
        month="2026-08",
        kind="deterioration_structural",
    )
    cap = alert(entity_id="COMP_TEST", month="2026-08", kind="cap_fired")
    write_entity(
        tmp_path,
        actions=[
            {
                "title": "Recuperar colchón de liquidez",
                "detail": "Revisar líneas disponibles y pagos próximos.",
                "uplift_tenths": 55,
                "new_score_tenths": 724,
            },
            {
                "title": "Reducir carga financiera",
                "detail": "Priorizar la deuda con mayor coste.",
                "uplift_tenths": 30,
                "new_score_tenths": 699,
            },
        ],
    )

    emails = notifications.build_demo_emails(
        [deterioration, cap],
        bundle_dir=tmp_path,
        sender="Embat X-Ray <xray@embat.test>",
        frontend_base_url="https://xray.example.test",
    )

    assert [(email.audience, email.alert_id) for email in emails] == [
        ("embat", deterioration["id"]),
        ("company", deterioration["id"]),
        ("embat", cap["id"]),
    ]
    internal = emails[0].message
    customer = emails[1].message
    assert internal["To"] == "cs-riesgo@embat.test"
    assert customer["To"] == "tesoreria+comp-test@empresa.test"
    assert (
        "febrero de 2026" in internal.get_body(preferencelist=("plain",)).get_content()
    )
    customer_text = customer.get_body(preferencelist=("plain",)).get_content()
    assert "Tu trayectoria financiera necesita atención" in customer_text
    assert "Tope aplicado" not in customer_text
    assert (
        "https://xray.example.test/?v=empresa&g=GROUP_TEST&emp=COMP_TEST&m=2026-08"
        in customer_text
    )
    assert "Liquidez: -12,0 puntos" in customer_text
    assert "Recuperar colchón de liquidez: +5,5 puntos" in customer_text
    assert "el score pasaría de 66,9 a 75,4" in customer_text
    customer_html = customer.get_body(preferencelist=("html",)).get_content()
    assert "Qué aporta y qué resta" in customer_html
    assert "Acciones para subir el score" in customer_html
    assert "Recuperar colchón de liquidez" in customer_html
    assert customer["X-XRay-Audience"] == "company"


def test_clear_mailpit_deletes_all_messages(monkeypatch: Any) -> None:
    captured: list[tuple[Request, float]] = []

    class Response:
        status = 200

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def fake_urlopen(request: Request, timeout: float) -> Response:
        captured.append((request, timeout))
        return Response()

    monkeypatch.setattr(notifications, "urlopen", fake_urlopen)

    notifications.clear_mailpit("http://mailpit:8025")

    request, timeout = captured[0]
    assert request.full_url == "http://mailpit:8025/api/v1/messages"
    assert request.get_method() == "DELETE"
    assert timeout == 5.0


def test_send_demo_emails_uses_one_smtp_connection(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    sent: list[EmailMessage] = []
    opened: list[tuple[str, int, float]] = []

    class SMTP:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            opened.append((host, port, timeout))

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def send_message(self, message: EmailMessage) -> None:
            sent.append(message)

    monkeypatch.setattr(notifications.smtplib, "SMTP", SMTP)
    write_entity(tmp_path)
    emails = notifications.build_demo_emails(
        [alert(entity_id="COMP_TEST", month="2026-08", kind="level_critical")],
        bundle_dir=tmp_path,
        sender="xray@embat.test",
        frontend_base_url="http://localhost:3000",
    )
    assert (
        "Sin acciones calculadas para este cierre"
        in emails[1].message.get_body(preferencelist=("html",)).get_content()
    )

    count = notifications.send_demo_emails(
        emails,
        smtp_host="mailpit",
        smtp_port=1025,
    )

    assert opened == [("mailpit", 1025, 10.0)]
    assert count == 2
    assert len(sent) == 2
