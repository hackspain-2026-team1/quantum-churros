"""Render engine alerts as demo emails and deliver them to a local SMTP sink."""

from __future__ import annotations

import html
import json
import re
import smtplib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

AlertRow = Mapping[str, Any]

MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
MONTH_PATTERN = re.compile(r"\b(\d{4})-(0[1-9]|1[0-2])\b")

INTERNAL_RECIPIENTS = {
    "deterioration_structural": "cs-riesgo@embat.test",
    "improvement_structural": "customer-success@embat.test",
    "level_critical": "cs-riesgo@embat.test",
    "cap_fired": "riesgo-producto@embat.test",
    "stale_feed": "data-ops@embat.test",
}
COMPANY_COPY = {
    "deterioration_structural": (
        "Tu trayectoria financiera necesita atención",
        "Hemos detectado un cambio sostenido, no un bache aislado.",
    ),
    "improvement_structural": (
        "Tu trayectoria financiera mejora",
        "La mejora se mantiene durante varios cierres.",
    ),
    "level_critical": (
        "Tu margen financiero está bajo presión",
        "El score ha entrado en el tramo crítico.",
    ),
    "stale_feed": (
        "Necesitamos volver a conectar tus datos",
        "No están llegando movimientos bancarios recientes.",
    ),
}
PILLAR_LABELS = {
    "liquidity": "Liquidez",
    "payments": "Pagos a proveedores",
    "collections": "Cobros de clientes",
    "activity": "Actividad",
    "debt": "Deuda",
}
BAND_LABELS = {
    "critical": "Crítico",
    "watch": "Vigilancia",
    "stable": "Estable",
    "solid": "Sólido",
}
CONFIDENCE_LABELS = {"high": "Alta", "medium": "Media", "low": "Baja"}
DIRECTION_LABELS = {
    "improving": "Mejora",
    "stable": "Estable",
    "deteriorating": "Deterioro",
    "perimeter_shift": "Cambio de perímetro",
}


@dataclass(frozen=True)
class DemoEmail:
    """One captured message and the engine alert that originated it."""

    alert_id: str
    audience: str
    message: EmailMessage


@dataclass(frozen=True)
class PillarInsight:
    """One dashboard driver, preserving the engine's integer-tenths arithmetic."""

    label: str
    contribution: int
    score: int | None
    note: str | None


@dataclass(frozen=True)
class ActionInsight:
    """One action exported by the engine for the alerted entity and close."""

    title: str
    detail: str | None
    uplift: int
    new_score: int


@dataclass(frozen=True)
class EntityInsight:
    """Dashboard context used by the email for the exact alerted close."""

    shown: int
    band: str
    confidence: str
    persistence_months: int
    direction: str
    pillars: tuple[PillarInsight, ...]
    actions: tuple[ActionInsight, ...]
    actions_target: int | None


def format_period(month: str) -> str:
    """Render YYYY-MM as a Spanish closing period."""
    match = MONTH_PATTERN.fullmatch(month)
    if match is None:
        raise ValueError(f"Invalid alert month: {month}")
    year, number = match.groups()
    return f"{MONTHS_ES[int(number) - 1]} de {year}"


def humanize_months(text: str) -> str:
    """Replace standalone YYYY-MM periods in engine prose."""

    def replace(match: re.Match[str]) -> str:
        return format_period(match.group(0))

    return MONTH_PATTERN.sub(replace, text)


def format_score(tenths: int) -> str:
    """Render integer score tenths with the Spanish decimal separator."""
    return f"{tenths / 10:.1f}".replace(".", ",")


def format_score_delta(tenths: int) -> str:
    """Render a signed integer-tenths score contribution."""
    if tenths == 0:
        return "0,0"
    sign = "+" if tenths > 0 else "-"
    return f"{sign}{format_score(abs(tenths))}"


def load_fired_alerts(
    bundle_dir: Path, month: str | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Load fired alerts from one close, defaulting to the newest close that fired anything."""
    path = bundle_dir / "alerts.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Bundle alerts not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Bundle alerts are not valid JSON: {path}") from exc

    rows = payload.get("alerts") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise TypeError(f"Bundle alerts have no alerts list: {path}")
    fired = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("state") == "fired"
        and isinstance(row.get("month"), str)
        and isinstance(row.get("kind"), str)
    ]
    if not fired:
        raise ValueError("Bundle contains no fired alerts")

    selected = month or max(str(row["month"]) for row in fired)
    format_period(selected)
    selected_rows = [row for row in fired if row["month"] == selected]
    if not selected_rows:
        raise ValueError(f"No fired alerts in {selected}")
    return selected, sorted(
        selected_rows, key=lambda row: (str(row["entity_id"]), str(row["kind"]))
    )


def load_entity_insight(bundle_dir: Path, alert: AlertRow) -> EntityInsight:
    """Load the same entity-month entry that powers the dashboard."""
    entity_id = str(alert["entity_id"])
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", entity_id) is None:
        raise ValueError(f"Invalid alert entity id: {entity_id}")
    folder = "groups" if alert["entity_kind"] == "group" else "companies"
    path = bundle_dir / folder / f"{entity_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Entity bundle not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Entity bundle is not valid JSON: {path}") from exc

    months = payload.get("months") if isinstance(payload, dict) else None
    if not isinstance(months, list):
        raise TypeError(f"Entity bundle has no months list: {path}")
    entry = next(
        (
            row
            for row in months
            if isinstance(row, dict) and row.get("month") == alert["month"]
        ),
        None,
    )
    if entry is None:
        raise ValueError(f"Entity bundle has no close {alert['month']}: {path}")

    shown = int(entry["shown"])
    if shown != int(alert["shown"]):
        raise ValueError(f"Alert and entity score differ for {alert['id']}")

    pillars = tuple(
        sorted(
            (
                PillarInsight(
                    label=PILLAR_LABELS.get(str(pillar["key"]), str(pillar["key"])),
                    contribution=int(pillar["contrib"]),
                    score=(
                        int(pillar["score"])
                        if pillar.get("score") is not None
                        else None
                    ),
                    note=(
                        str(pillar["note"])
                        if isinstance(pillar.get("note"), str)
                        else None
                    ),
                )
                for pillar in entry.get("pillars", [])
                if isinstance(pillar, dict)
            ),
            key=lambda pillar: abs(pillar.contribution),
            reverse=True,
        )
    )
    actions = tuple(
        sorted(
            (
                ActionInsight(
                    title=str(action["title"]),
                    detail=(
                        str(action["detail"])
                        if isinstance(action.get("detail"), str)
                        else None
                    ),
                    uplift=int(action["uplift_tenths"]),
                    new_score=int(action["new_score_tenths"]),
                )
                for action in entry.get("actions", [])
                if isinstance(action, dict)
            ),
            key=lambda action: action.uplift,
            reverse=True,
        )
    )
    combined = entry.get("actions_combined")
    if isinstance(combined, dict):
        actions_target = int(combined["new_score"])
    elif actions:
        actions_target = max(action.new_score for action in actions)
    else:
        actions_target = None
    verdict = entry.get("verdict") if isinstance(entry.get("verdict"), dict) else {}
    confidence = entry.get("conf") if isinstance(entry.get("conf"), dict) else {}
    return EntityInsight(
        shown=shown,
        band=BAND_LABELS.get(str(entry["band"]), str(entry["band"])),
        confidence=CONFIDENCE_LABELS.get(
            str(confidence.get("label")), str(confidence.get("label", "—"))
        ),
        persistence_months=int(verdict.get("persistence_months", 0)),
        direction=DIRECTION_LABELS.get(
            str(verdict.get("direction")), str(verdict.get("direction", "—"))
        ),
        pillars=pillars,
        actions=actions,
        actions_target=actions_target,
    )


def entity_url(alert: AlertRow, frontend_base_url: str) -> str:
    """Deep link to the entity and close named by an alert."""
    group_id = str(alert["group_id"])
    if alert["entity_kind"] == "group":
        query = {"v": "organizacion", "g": group_id, "m": str(alert["month"])}
    else:
        query = {
            "v": "empresa",
            "g": group_id,
            "emp": str(alert["entity_id"]),
            "m": str(alert["month"]),
        }
    return f"{frontend_base_url.rstrip('/')}/?{urlencode(query, quote_via=quote)}"


def _plain_body(
    alert: AlertRow,
    insight: EntityInsight,
    headline: str,
    detail: str,
    link: str,
) -> str:
    period = format_period(str(alert["month"]))
    drivers = "\n".join(
        f"- {pillar.label}: {format_score_delta(pillar.contribution)} puntos. "
        f"{pillar.note or 'Sin nota adicional.'}"
        for pillar in insight.pillars[:3]
    )
    if insight.actions:
        actions = "\n".join(
            f"- {action.title}: {format_score_delta(action.uplift)} puntos; "
            f"score estimado {format_score(action.new_score)}."
            for action in insight.actions
        )
        target = (
            f"Si sigues estas acciones, el score pasaría de {format_score(insight.shown)} "
            f"a {format_score(insight.actions_target or insight.shown)}.\n"
        )
    else:
        target = ""
        actions = "Sin acciones calculadas para este cierre."
    return (
        f"{headline}\n\n"
        f"{detail}\n"
        f"{humanize_months(str(alert['detail']))}\n\n"
        f"Entidad: {alert['entity_id']}\n"
        f"Cierre: {period}\n"
        f"Score: {format_score(insight.shown)}\n"
        f"Banda: {insight.band}\n"
        f"Trayectoria: {insight.direction}\n"
        f"Confianza: {insight.confidence}\n"
        f"Persistencia: {insight.persistence_months} cierres\n\n"
        f"Qué aporta y qué resta\n{drivers}\n\n"
        f"Acciones para subir el score\n{target}{actions}\n\n"
        f"Abrir el diagnóstico: {link}\n\n"
        "Correo capturado por Mailpit. No se ha enviado a un destinatario real."
    )


def _drivers_html(insight: EntityInsight) -> str:
    cards: list[str] = []
    for pillar in insight.pillars[:3]:
        positive = pillar.contribution > 0
        negative = pillar.contribution < 0
        color = "#198754" if positive else "#b42318" if negative else "#637786"
        verb = "aporta" if positive else "resta" if negative else "no mueve"
        observed = (
            format_score(pillar.score) if pillar.score is not None else "Sin dato"
        )
        note = html.escape(pillar.note or "Sin nota adicional.")
        cards.append(
            f"""\
<tr>
  <td style="padding:0 0 10px">
    <table role="presentation" width="100%" style="border:1px solid #dfe7ec;border-radius:12px">
      <tr>
        <td style="padding:14px 16px">
          <p style="margin:0 0 4px;color:#637786;font-size:11px;text-transform:uppercase;letter-spacing:.08em">
            Pilar · {verb} · observado {html.escape(observed)}
          </p>
          <p style="margin:0;color:#102431;font-size:16px;font-weight:700">
            {html.escape(pillar.label)}
            <span style="float:right;color:{color};font-family:monospace">
              {html.escape(format_score_delta(pillar.contribution))}
            </span>
          </p>
          <p style="margin:8px 0 0;color:#637786;font-size:13px;line-height:1.5">{note}</p>
        </td>
      </tr>
    </table>
  </td>
</tr>"""
        )
    return "".join(cards)


def _actions_html(insight: EntityInsight) -> str:
    if not insight.actions:
        return """\
<table role="presentation" width="100%" style="border:1px dashed #b9c8d2;border-radius:12px">
  <tr><td style="padding:16px">
    <p style="margin:0;color:#102431;font-weight:700">Sin acciones calculadas para este cierre</p>
    <p style="margin:6px 0 0;color:#637786;font-size:13px;line-height:1.5">
      El dashboard tampoco muestra acciones para este periodo.
    </p>
  </td></tr>
</table>"""

    target = insight.actions_target or insight.shown
    rows = []
    for action in insight.actions:
        detail = (
            f'<p style="margin:6px 0 0;color:#637786;font-size:13px;line-height:1.5">'
            f"{html.escape(action.detail)}</p>"
            if action.detail
            else ""
        )
        rows.append(
            f"""\
<tr>
  <td style="padding:0 0 10px">
    <table role="presentation" width="100%" style="background:#fff;border:1px solid #cde8d8;border-radius:12px">
      <tr><td style="padding:14px 16px">
        <p style="margin:0;color:#102431;font-weight:700">{html.escape(action.title)}</p>
        {detail}
        <p style="margin:8px 0 0;color:#198754;font-family:monospace;font-weight:700">
          {html.escape(format_score_delta(action.uplift))} puntos · score {html.escape(format_score(action.new_score))}
        </p>
      </td></tr>
    </table>
  </td>
</tr>"""
        )
    return f"""\
<p style="margin:0 0 14px;color:#285c3c;line-height:1.5">
  Si sigues estas acciones, tu score pasaría de
  <strong>{html.escape(format_score(insight.shown))}</strong> a
  <strong>{html.escape(format_score(target))}</strong>.
</p>
<table role="presentation" width="100%">{"".join(rows)}</table>"""


def _message(
    *,
    alert: AlertRow,
    insight: EntityInsight,
    audience: str,
    sender: str,
    recipient: str,
    subject: str,
    headline: str,
    detail: str,
    frontend_base_url: str,
) -> DemoEmail:
    alert_id = str(alert["id"])
    period = format_period(str(alert["month"]))
    link = entity_url(alert, frontend_base_url)
    text = _plain_body(alert, insight, headline, detail, link)
    kind = str(alert["kind"])
    tone = (
        ("#b42318", "#fff1ef")
        if kind in {"deterioration_structural", "level_critical"}
        else ("#198754", "#edf9f1")
        if kind == "improvement_structural"
        else ("#9a6700", "#fff8e5")
    )
    persistence = (
        f"{insight.persistence_months} cierre"
        if insight.persistence_months == 1
        else f"{insight.persistence_months} cierres"
    )
    html_body = f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;background:#f2f7f9;font-family:Arial,sans-serif;color:#102431">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f2f7f9">
    <tr><td align="center" style="padding:28px 14px">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="max-width:680px;background:#fff;border:1px solid #dfe7ec;border-radius:18px;overflow:hidden">
        <tr><td style="padding:20px 26px;background:#102f43;color:#fff">
          <p style="margin:0;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#8edce5">
            Embat X-Ray · monitor financiero
          </p>
          <p style="margin:6px 0 0;font-family:monospace;font-size:18px;font-weight:700">
            {html.escape(str(alert["entity_id"]))}
          </p>
        </td></tr>
        <tr><td style="padding:26px">
          <span style="display:inline-block;padding:6px 10px;border-radius:999px;color:{tone[0]};
                       background:{tone[1]};font-size:12px;font-weight:700">
            {html.escape(insight.direction)} · {html.escape(period)}
          </span>
          <h1 style="margin:16px 0 8px;font-size:26px;line-height:1.2">{html.escape(headline)}</h1>
          <p style="margin:0 0 20px;color:#637786;font-size:15px;line-height:1.6">{html.escape(detail)}</p>

          <table role="presentation" width="100%" style="background:#f8fbfc;border:1px solid #dfe7ec;border-radius:14px">
            <tr>
              <td width="34%" style="padding:18px;border-right:1px solid #dfe7ec;text-align:center">
                <p style="margin:0;font-family:monospace;font-size:34px;font-weight:700">
                  {html.escape(format_score(insight.shown))}
                </p>
                <p style="margin:4px 0 0;color:#637786;font-size:10px;letter-spacing:.14em;text-transform:uppercase">Score</p>
              </td>
              <td style="padding:18px">
                <table role="presentation" width="100%" style="font-size:13px">
                  <tr><td style="padding:3px;color:#637786">Banda</td><td style="padding:3px;font-weight:700">{html.escape(insight.band)}</td></tr>
                  <tr><td style="padding:3px;color:#637786">Confianza</td><td style="padding:3px;font-weight:700">{html.escape(insight.confidence)}</td></tr>
                  <tr><td style="padding:3px;color:#637786">Persistencia</td><td style="padding:3px;font-weight:700">{html.escape(persistence)}</td></tr>
                </table>
              </td>
            </tr>
          </table>

          <table role="presentation" width="100%" style="margin-top:18px;background:{tone[1]};border-left:4px solid {tone[0]};border-radius:10px">
            <tr><td style="padding:16px">
              <p style="margin:0 0 5px;font-size:12px;font-weight:700;color:{tone[0]};text-transform:uppercase">Qué hemos detectado</p>
              <p style="margin:0;font-size:14px;line-height:1.6">{html.escape(humanize_months(str(alert["detail"])))}</p>
            </td></tr>
          </table>

          <h2 style="margin:28px 0 12px;font-size:18px">Qué aporta y qué resta</h2>
          <table role="presentation" width="100%">{_drivers_html(insight)}</table>

          <table role="presentation" width="100%" style="margin-top:18px;background:#edf9f1;border:1px solid #cde8d8;border-radius:14px">
            <tr><td style="padding:20px">
              <p style="margin:0 0 4px;color:#285c3c;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase">Qué hacer ahora</p>
              <h2 style="margin:0 0 14px;font-size:18px">Acciones para subir el score</h2>
              {_actions_html(insight)}
            </td></tr>
          </table>

          <p style="margin:24px 0 0">
            <a href="{html.escape(link)}"
               style="display:inline-block;padding:12px 18px;border-radius:9px;background:#102f43;color:#fff;text-decoration:none;font-weight:700">
              Abrir el diagnóstico completo
            </a>
          </p>
          <p style="margin:20px 0 0;color:#637786;font-size:11px;line-height:1.5">
            Correo capturado por Mailpit. No se ha enviado a un destinatario real.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(
        idstring=re.sub(r"[^A-Za-z0-9_.-]", "-", f"{alert_id}-{audience}"),
        domain="xray.local",
    )
    message["X-XRay-Alert-ID"] = alert_id
    message["X-XRay-Audience"] = audience
    message.set_content(text)
    message.add_alternative(html_body, subtype="html")
    return DemoEmail(alert_id=alert_id, audience=audience, message=message)


def build_demo_emails(
    alerts: Iterable[AlertRow],
    *,
    bundle_dir: Path,
    sender: str,
    frontend_base_url: str,
) -> list[DemoEmail]:
    """Build internal and company-facing messages allowed by the demo routing policy."""
    emails: list[DemoEmail] = []
    for alert in alerts:
        kind = str(alert["kind"])
        insight = load_entity_insight(bundle_dir, alert)
        internal_recipient = INTERNAL_RECIPIENTS.get(kind)
        if internal_recipient is not None:
            emails.append(
                _message(
                    alert=alert,
                    insight=insight,
                    audience="embat",
                    sender=sender,
                    recipient=internal_recipient,
                    subject=f"[X-Ray] {alert['title']} · {alert['entity_id']}",
                    headline=f"{alert['title']} · {alert['entity_id']}",
                    detail=humanize_months(str(alert["detail"])),
                    frontend_base_url=frontend_base_url,
                )
            )

        company_copy = COMPANY_COPY.get(kind)
        if company_copy is not None:
            headline, detail = company_copy
            entity_slug = re.sub(
                r"[^a-z0-9]+", "-", str(alert["entity_id"]).lower()
            ).strip("-")
            emails.append(
                _message(
                    alert=alert,
                    insight=insight,
                    audience="company",
                    sender=sender,
                    recipient=f"tesoreria+{entity_slug}@empresa.test",
                    subject=f"{headline} · {format_period(str(alert['month']))}",
                    headline=headline,
                    detail=detail,
                    frontend_base_url=frontend_base_url,
                )
            )
    return emails


def clear_mailpit(api_url: str, timeout: float = 5.0) -> None:
    """Delete prior captured messages so every demo starts from a deterministic inbox."""
    request = Request(f"{api_url.rstrip('/')}/api/v1/messages", method="DELETE")
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Mailpit clear failed with HTTP {response.status}")


def send_demo_emails(
    emails: Iterable[DemoEmail],
    *,
    smtp_host: str,
    smtp_port: int,
    timeout: float = 10.0,
) -> int:
    """Send every rendered message through the configured SMTP sink."""
    messages = list(emails)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as client:
        for email in messages:
            client.send_message(email.message)
    return len(messages)


def dispatch_demo_notifications(
    bundle_dir: Path,
    *,
    month: str | None,
    clear: bool,
    smtp_host: str,
    smtp_port: int,
    sender: str,
    frontend_base_url: str,
    mailpit_api_url: str,
) -> tuple[str, int]:
    """Load one close, optionally reset Mailpit, and deliver all routed demo emails."""
    selected, alerts = load_fired_alerts(bundle_dir, month)
    emails = build_demo_emails(
        alerts,
        bundle_dir=bundle_dir,
        sender=sender,
        frontend_base_url=frontend_base_url,
    )
    if clear:
        clear_mailpit(mailpit_api_url)
    return selected, send_demo_emails(emails, smtp_host=smtp_host, smtp_port=smtp_port)
