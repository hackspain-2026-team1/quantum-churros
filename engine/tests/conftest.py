"""Shared fixtures: synthetic dataset generator, dataset transforms, random panel rows.

The generator writes the eight CSVs with the exact headers of the challenge
files. Everything is seeded and written with the stdlib ``csv`` module, so the
files are byte-identical for a given (n_groups, seed).
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import os
import random
from collections import defaultdict
from dataclasses import dataclass, fields, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from xray_engine.contracts import PANEL_UNITS, PanelRow, Params
from xray_engine.params import load_params

HEADERS: dict[str, list[str]] = {
    "groups.csv": ["group_id", "erp", "n_companies_in_sample"],
    "companies.csv": ["company_id", "group_id", "country", "currency", "erp", "created_at"],
    "banking_products.csv": [
        "product_id", "company_id", "label", "type", "bank_name", "service", "currency", "created_at",
    ],
    "debt_products.csv": [
        "product_id", "company_id", "label", "type", "bank_name", "service", "currency", "created_at",
        "granted", "outstanding", "liquidity",
    ],
    "debt_schedule_config.csv": [
        "product_id", "company_id", "settlement_product_id", "currency", "amortization_type",
        "interest_calc_method", "amortising_frequency", "granted_balance", "outstanding_balance",
        "total_periods", "next_payment_date", "last_payment_date", "annual_interest_rate_or_spread",
        "interest_type",
    ],
    "transactions.csv": [
        "transaction_id", "company_id", "product_id", "date", "value_date", "amount", "exchange_rate",
        "status", "accounting_status", "category", "description", "counterparty_id",
    ],
    "invoices.csv": [
        "operation_id", "company_id", "document_type", "issuance_date", "due_date", "payment_date",
        "amount", "pending_amount", "currency", "accounting_currency", "exchange_rate", "status",
        "concept", "counterparty_id",
    ],
    "balances.csv": [
        "product_id", "company_id", "date", "balance", "available", "granted", "liquidity", "countable",
    ],
}
MONEY_COLUMNS: dict[str, list[str]] = {
    "debt_products.csv": ["granted", "outstanding", "liquidity"],
    "debt_schedule_config.csv": ["granted_balance", "outstanding_balance"],
    "transactions.csv": ["amount"],
    "invoices.csv": ["amount", "pending_amount"],
    "balances.csv": ["balance", "available", "granted", "liquidity", "countable"],
}
FIRST_MONTH = date(2024, 9, 1)
LAST_MONTH = date(2026, 8, 1)
AS_OF = date(2026, 9, 1)
SENTINEL_CENTS = -99_999_999_900
SENTINEL_ABS_CENTS = 90_000_000_000


# --------------------------------------------------------------------------
# pytest plumbing
# --------------------------------------------------------------------------


def _real_data_dir() -> Path | None:
    value = os.environ.get("XRAY_DATA")
    if not value:
        return None
    path = Path(value)
    return path if (path / "transactions.csv").is_file() else None


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "dataset: needs the real dataset; set XRAY_DATA to its folder"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _real_data_dir() is not None:
        return
    skip = pytest.mark.skip(reason="XRAY_DATA does not point to a dataset folder")
    for item in items:
        if "dataset" in item.keywords:
            item.add_marker(skip)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def month_add(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def month_end(month: date) -> date:
    return date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def month_range(first: date, last: date) -> list[date]:
    months = []
    current = first
    while current <= last:
        months.append(current)
        current = month_add(current, 1)
    return months


def money(cents: int) -> str:
    whole, fraction = divmod(abs(cents), 100)
    text = f"{whole}.{fraction:02d}".rstrip("0").rstrip(".")
    return f"-{text}" if cents < 0 else text


def to_cents(text: str) -> int:
    return int((Decimal(text) * 100).to_integral_value())


def _stamp(day: date, clock: str = "00:00:00") -> str:
    return f"{day.isoformat()} {clock}"


def _split(rng: random.Random, total: int, count: int) -> list[int]:
    weights = [rng.uniform(0.4, 1.6) for _ in range(count)]
    scale = total / sum(weights)
    return [max(100, int(weight * scale)) for weight in weights]


# --------------------------------------------------------------------------
# handles
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MirrorPair:
    out_id: str
    in_id: str
    scope: str  # intra_company | intra_group
    out_category: str
    in_category: str
    day_offset: int  # date of the positive leg minus date of the negative leg
    amount_cents: int
    month: date
    group_id: str
    ambiguous: bool  # same key and day as another pair: only the count is defined


@dataclass(frozen=True)
class SyntheticDataset:
    path: Path
    seed: int
    first_month: date
    last_month: date
    as_of: date
    group_ids: tuple[str, ...]
    company_ids: tuple[str, ...]
    companies_by_group: dict[str, tuple[str, ...]]
    company_first_month: dict[str, date]
    product_first_month: dict[str, date]
    row_counts: dict[str, int]
    mirror_pairs: tuple[MirrorPair, ...]
    dash_installment_ids: tuple[str, ...]
    dash_drawdown_ids: tuple[str, ...]
    dash_unrecoverable_ids: tuple[str, ...]
    newline_transaction_id: str
    pending_transaction_ids: tuple[str, ...]
    blank_status_transaction_ids: tuple[str, ...]
    usd_product_id: str
    usd_company_id: str
    fx_excluded_product_id: str
    credit_line_product_id: str
    credit_line_company_id: str
    credit_line_granted_cents: int
    credit_line_drawn_cents: int
    loan_product_id: str
    guarantee_product_id: str
    sentinel_product_id: str
    own_date_anchor_product_id: str
    late_member_company_id: str
    late_member_group_id: str
    late_member_first_month: date
    mid_window_product_id: str
    mid_window_company_id: str
    mid_window_first_month: date
    swept_company_id: str
    treasury_company_id: str
    stamped_company_id: str
    non_stamped_company_id: str
    deteriorating_company_id: str
    late_ap_invoice_ids: tuple[str, ...]
    unpaid_ap_invoice_ids: tuple[str, ...]
    late_ar_invoice_ids: tuple[str, ...]
    unpaid_ar_invoice_ids: tuple[str, ...]
    ignored_invoice_ids: tuple[str, ...]  # other document types, cancelled, impossible dates
    no_invoice_group_id: str
    no_debt_group_id: str
    short_history_company_id: str
    short_history_group_id: str
    # oracle: booked end-of-month balance per product, integer cents
    month_end_balance_cents: dict[tuple[str, date], int]


# --------------------------------------------------------------------------
# generator
# --------------------------------------------------------------------------


class _Builder:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.rows: dict[str, list[dict[str, str]]] = {name: [] for name in HEADERS}
        self.company_group: dict[str, str] = {}
        self.company_erp: dict[str, str] = {}
        self.product_company: dict[str, str] = {}
        self.product_currency: dict[str, str] = {}
        self.opening: dict[str, int] = {}
        self.final_target: dict[str, int] = {}
        self.ledger: dict[str, list[tuple[date, int]]] = defaultdict(list)
        self.used: set[tuple[str, str, date, int]] = set()
        self.counter = 0
        self.products = 0
        self.companies = 0
        self.lists: dict[str, list] = defaultdict(list)
        self.single: dict[str, object] = {}

    # ids ------------------------------------------------------------------
    def _hex(self, kind: str) -> str:
        self.counter += 1
        return hashlib.md5(f"{kind}:{self.seed}:{self.counter}".encode()).hexdigest()

    def counterparty(self) -> str:
        return f"COUNTERPARTY_{self.rng.randint(1, 400):05d}"

    # master data ----------------------------------------------------------
    def group(self, group_id: str, erp: str, size: int) -> None:
        self.rows["groups.csv"].append(
            {"group_id": group_id, "erp": erp, "n_companies_in_sample": str(size)}
        )

    def company(
        self, group_id: str, *, country: str = "", currency: str = "EUR", erp: str = "",
        created: date = date(2024, 6, 3),
    ) -> str:
        self.companies += 1
        company_id = f"COMP_{self.companies:04d}"
        self.company_group[company_id] = group_id
        self.company_erp[company_id] = erp
        self.rows["companies.csv"].append(
            {
                "company_id": company_id, "group_id": group_id, "country": country,
                "currency": currency, "erp": erp, "created_at": _stamp(created, "11:08:05"),
            }
        )
        return company_id

    def _product_id(self, company_id: str, currency: str) -> str:
        self.products += 1
        product_id = f"PRODUCT_{self.products:05d}"
        self.product_company[product_id] = company_id
        self.product_currency[product_id] = currency
        return product_id

    def bank_product(
        self, company_id: str, kind: str = "checking", *, currency: str = "EUR",
        opening: int = 0, bank: str = "Banco Santander Empresas", service: str = "santander_emp",
        created: date = date(2024, 6, 3),
    ) -> str:
        product_id = self._product_id(company_id, currency)
        self.opening[product_id] = opening
        self.rows["banking_products.csv"].append(
            {
                "product_id": product_id, "company_id": company_id,
                "label": f"{kind.upper()}_{self.products:02d}", "type": kind, "bank_name": bank,
                "service": service, "currency": currency, "created_at": _stamp(created, "15:46:46"),
            }
        )
        return product_id

    def debt_product(
        self, company_id: str, kind: str, *, granted: int | None, outstanding: int,
        liquidity: int | None = None, bank: str = "BBVA", service: str = "bbva_emp",
        created: date = date(2024, 6, 3),
    ) -> str:
        product_id = self._product_id(company_id, "EUR")
        self.rows["debt_products.csv"].append(
            {
                "product_id": product_id, "company_id": company_id,
                "label": f"{kind.upper()}_{self.products:02d}", "type": kind, "bank_name": bank,
                "service": service, "currency": "EUR", "created_at": _stamp(created, "12:50:43"),
                "granted": "" if granted is None else money(granted),
                "outstanding": money(outstanding),
                "liquidity": "" if liquidity is None else money(liquidity),
            }
        )
        return product_id

    # transactions ---------------------------------------------------------
    def _key(self, product_id: str, day: date, cents: int) -> tuple[str, str, date, int]:
        group_id = self.company_group[self.product_company[product_id]]
        return (group_id, self.product_currency[product_id], day.replace(day=1), abs(cents))

    def reserve(self, product_id: str, day: date, cents: int, step: int = 1) -> int:
        """Nearest free amount: no other row of the group shares currency, month and |cents|."""
        while cents == 0 or self._key(product_id, day, cents) in self.used:
            cents += step
        self.used.add(self._key(product_id, day, cents))
        return cents

    def txn(
        self, product_id: str, day: date, cents: int, category: str, description: str, *,
        status: str = "booked", counterparty: str = "", unique: bool = True,
    ) -> str:
        if unique:
            cents = self.reserve(product_id, day, cents, 1 if cents > 0 else -1)
        company_id = self.product_company[product_id]
        transaction_id = self._hex("txn")
        if status == "booked" and self.rng.random() < 0.03:
            status = ""
            self.lists["blank_status"].append(transaction_id)
        reconciled = "RECONCILIATION_COMPLETED" if self.company_erp[company_id] else ""
        rate = "1" if self.product_currency[product_id] == "EUR" else "0.92"
        self.rows["transactions.csv"].append(
            {
                "transaction_id": transaction_id, "company_id": company_id,
                "product_id": product_id, "date": _stamp(day), "value_date": _stamp(day),
                "amount": money(cents), "exchange_rate": rate, "status": status,
                "accounting_status": reconciled, "category": category,
                "description": description, "counterparty_id": counterparty,
            }
        )
        if status != "pending":
            self.ledger[product_id].append((day, cents))
        return transaction_id

    def mirror(
        self, out_product: str, in_product: str, day: date, cents: int, *,
        out_category: str = "transfer", in_category: str = "transfer", offset: int = 0,
        ambiguous: bool = False, reserve: bool = True,
    ) -> None:
        cents = abs(cents)
        if reserve:
            cents = self.reserve(out_product, day, cents, -1 if cents > 1 else 1)
        in_day = day + timedelta(days=offset)
        assert in_day.month == day.month, "mirror legs must share the month"
        out_id = self.txn(
            out_product, day, -cents, out_category, "TRASPASO ENTRE CUENTAS [COMPANY]",
            unique=False,
        )
        in_id = self.txn(
            in_product, in_day, cents, in_category, "Traspaso automatico [ACCOUNT]", unique=False
        )
        out_company = self.product_company[out_product]
        in_company = self.product_company[in_product]
        self.lists["mirror_pairs"].append(
            MirrorPair(
                out_id=out_id, in_id=in_id,
                scope="intra_company" if out_company == in_company else "intra_group",
                out_category=out_category, in_category=in_category, day_offset=offset,
                amount_cents=cents, month=day.replace(day=1),
                group_id=self.company_group[out_company], ambiguous=ambiguous,
            )
        )

    def balance(self, product_id: str, on: date) -> int:
        return self.opening.get(product_id, 0) + sum(
            cents for day, cents in self.ledger.get(product_id, []) if day <= on
        )

    def operating_month(
        self, product_id: str, month: date, inflow: int, outflow: int, *, payroll: bool = True,
        last_day: int | None = None,
    ) -> None:
        rng = self.rng
        days = last_day or calendar.monthrange(month.year, month.month)[1]
        for cents in _split(rng, inflow, rng.randint(6, 9)):
            category = rng.choices(
                ["collection", "bulk_collection", "pos_settlement", "cash_settlement"],
                [0.8, 0.08, 0.07, 0.05],
            )[0]
            counterparty = self.counterparty() if rng.random() < 0.5 else ""
            self.txn(
                product_id, month.replace(day=rng.randint(1, days)), cents, category,
                f"TRANSFERENCIA DE {counterparty or '[COMPANY]'} FRA [NUM]",
                counterparty=counterparty,
            )
        shares = {"salary": 0.25, "social_security": 0.08, "tax": 0.07} if payroll else {}
        fixed = {
            "salary": (min(28, days), "NOMINA [PERSON]"),
            "social_security": (days, "SEGUROS SOCIALES TGSS [NUM]"),
            "tax": (min(20, days), "AEAT IMPUESTOS MODELO 303"),
        }
        spent = 0
        for category, share in shares.items():
            day, text = fixed[category]
            cents = int(outflow * share)
            spent += cents
            self.txn(product_id, month.replace(day=day), -cents, category, text)
        for cents in _split(rng, int(outflow * 0.05), 3):
            spent += cents
            self.txn(
                product_id, month.replace(day=rng.randint(1, days)), -cents, "utility",
                "RECIBO [COMPANY] SUMINISTRO [NUM]",
            )
        for cents in _split(rng, max(300, int(outflow * 0.01)), 2):
            spent += cents
            self.txn(
                product_id, month.replace(day=rng.randint(1, days)), -cents, "fee",
                "COMISION MANTENIMIENTO",
            )
        for cents in _split(rng, max(1000, outflow - spent), rng.randint(6, 9)):
            category = "bulk_payment" if rng.random() < 0.1 else "payment"
            counterparty = self.counterparty() if rng.random() < 0.5 else ""
            self.txn(
                product_id, month.replace(day=rng.randint(1, days)), -cents, category,
                f"PAGO FACTURA [NUM] {counterparty or '[COMPANY]'}", counterparty=counterparty,
            )
        # uncategorised noise: two recoverable narratives, one opaque
        day = month.replace(day=rng.randint(1, days))
        self.txn(product_id, day, -rng.randint(1_000, 9_000), "-", "COMISION TRANSFERENCIA [NUM]")
        self.txn(product_id, day, -rng.randint(90_000, 300_000), "-", "NOMINA [PERSON] [NUM]")
        opaque = self.txn(
            product_id, day, rng.choice([-1, 1]) * rng.randint(5_000, 80_000), "-", "[X] [X] [NUM]"
        )
        self.lists["dash_unrecoverable"].append(opaque)

    # invoices -------------------------------------------------------------
    def invoice(
        self, company_id: str, issued: date, due: date, paid: date | None, cents: int, *,
        status: str | None = None, document_type: str = "invoice", currency: str = "EUR",
        pending: int | None = None,
    ) -> str:
        operation_id = self._hex("inv")
        settled = paid is not None and paid <= AS_OF
        if status is None:
            status = "paid" if settled else ("overdue" if due < AS_OF else "pending")
        if pending is None:
            pending = 0 if status == "paid" else cents
        shown = paid if settled or status not in ("overdue", "pending") else due
        self.rows["invoices.csv"].append(
            {
                "operation_id": operation_id, "company_id": company_id,
                "document_type": document_type, "issuance_date": _stamp(issued),
                "due_date": _stamp(due), "payment_date": _stamp(shown or due),
                "amount": money(cents), "pending_amount": money(pending), "currency": currency,
                "accounting_currency": "EUR", "exchange_rate": "1" if currency == "EUR" else "0.92",
                "status": status, "concept": "Factura [X]/[NUM]. [X] Servicios",
                "counterparty_id": self.counterparty(),
            }
        )
        return operation_id

    def invoice_month(
        self, company_id: str, month: date, *, stamped: bool, late_share: float,
        unpaid_share: float, ticket: int, track: bool = False,
    ) -> None:
        rng = self.rng
        days = calendar.monthrange(month.year, month.month)[1]
        for side, sign in (("ar", 1), ("ap", -1)):
            for _ in range(8):
                issued = month.replace(day=rng.randint(1, days))
                cents = sign * rng.randint(ticket // 2, ticket * 2)
                if stamped:
                    unpaid = rng.random() < unpaid_share
                    self.invoice(company_id, issued, issued, None if unpaid else issued, cents)
                    continue
                due = issued + timedelta(days=rng.choice([30, 30, 30, 60]))
                draw = rng.random()
                if draw < unpaid_share:
                    operation_id = self.invoice(company_id, issued, due, None, cents)
                    kind = "unpaid"
                elif draw < unpaid_share + late_share:
                    paid = due + timedelta(days=rng.randint(5, 45))
                    operation_id = self.invoice(company_id, issued, due, paid, cents)
                    kind = "late" if paid <= AS_OF else "unpaid"
                else:
                    paid = due - timedelta(days=rng.choice([0, 0, 0, 5]))
                    operation_id = self.invoice(company_id, issued, due, paid, cents)
                    kind = "on_time" if paid <= AS_OF else "unpaid"
                if track and kind in ("late", "unpaid"):
                    self.lists[f"{kind}_{side}"].append(operation_id)

    # output ---------------------------------------------------------------
    def finish_balances(self, own_date_product: str, sentinel_product: str) -> None:
        debt_rows = {row["product_id"]: row for row in self.rows["debt_products.csv"]}
        for product_id, target in self.final_target.items():
            self.opening[product_id] = target - sum(
                cents for _, cents in self.ledger.get(product_id, [])
            )
        for row in self.rows["banking_products.csv"] + self.rows["debt_products.csv"]:
            product_id = row["product_id"]
            on = date(2026, 8, 28) if product_id == own_date_product else AS_OF
            granted = liquidity = countable = ""
            if product_id in debt_rows and product_id not in self.final_target:
                cents = to_cents(debt_rows[product_id]["outstanding"])
                granted = debt_rows[product_id]["granted"]
            else:
                cents = self.balance(product_id, on)
                if product_id in debt_rows:
                    granted = debt_rows[product_id]["granted"]
                    liquidity = money(cents - to_cents(granted))
                elif row["type"] == "card":
                    granted = "-6000"
                    liquidity = money(cents + 600_000)
                else:
                    countable = money(cents) if self.rng.random() < 0.5 else ""
            if product_id == sentinel_product:
                cents, liquidity, countable = SENTINEL_CENTS, "0", "0"
            self.rows["balances.csv"].append(
                {
                    "product_id": product_id, "company_id": row["company_id"], "date": _stamp(on),
                    "balance": money(cents), "available": "", "granted": granted,
                    "liquidity": liquidity, "countable": countable,
                }
            )

    def write(self, path: Path) -> dict[str, int]:
        path.mkdir(parents=True, exist_ok=True)
        keys = {
            "transactions.csv": "transaction_id", "invoices.csv": "operation_id",
            "balances.csv": "product_id",
        }
        counts = {}
        for name, header in HEADERS.items():
            rows = self.rows[name]
            if name in keys:  # hashed ids: a stable pseudo-random file order
                rows = sorted(rows, key=lambda row: row[keys[name]])
            with (path / name).open("w", newline="", encoding="utf-8") as target:
                writer = csv.DictWriter(target, fieldnames=header, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            counts[name] = len(rows)
        return counts


def _core_groups(b: _Builder) -> None:
    rng = b.rng
    months = month_range(FIRST_MONTH, LAST_MONTH)

    # G1: treasury centre + swept subsidiary + member joining 5 months late
    b.group("GROUP_0001", "Netsuite", 3)
    treasury = b.company("GROUP_0001", country="ES", erp="netsuite")
    swept = b.company("GROUP_0001", erp="netsuite")
    late = b.company("GROUP_0001", country="ES", erp="netsuite", created=date(2025, 2, 1))
    main = b.bank_product(treasury, opening=25_000_000)
    second = b.bank_product(treasury, opening=4_000_000, bank="BBVA", service="bbva_emp")
    usd = b.bank_product(treasury, currency="USD", opening=3_000_000)
    line = b.debt_product(
        treasury, "lineofcredit", granted=-30_000_000, outstanding=-12_000_000, liquidity=18_000_000
    )
    b.final_target[line] = -12_000_000
    loan = b.debt_product(treasury, "loan", granted=-25_000_000, outstanding=-18_000_000)
    b.rows["debt_schedule_config.csv"].append(
        {
            "product_id": loan, "company_id": treasury, "settlement_product_id": main,
            "currency": "EUR", "amortization_type": "constant quote",
            "interest_calc_method": "30/360", "amortising_frequency": "monthly",
            "granted_balance": "250000", "outstanding_balance": "231400.5", "total_periods": "60",
            "next_payment_date": _stamp(date(2024, 7, 5)),
            "last_payment_date": _stamp(date(2024, 6, 5), "12:31:20"),
            "annual_interest_rate_or_spread": "0.04", "interest_type": "fixed",
        }
    )
    swept_account = b.bank_product(swept, opening=0, bank="Banco Sabadell T. sec - CAL", service="sabadell_sec")
    late_account = b.bank_product(late, opening=6_000_000, created=date(2025, 2, 1))
    offsets = [0, 0, 0, 1, 0, -1, 0, 2, 0, -2]
    labels = [("transfer", "transfer"), ("payment", "collection"), ("-", "-")]
    for index, month in enumerate(months):
        b.operating_month(main, month, 18_000_000, 19_000_000)
        b.txn(usd, month.replace(day=9), 1_200_000 + index * 1_000, "collection",
              "WIRE TRANSFER [COMPANY] INV [NUM]")
        b.txn(main, month.replace(day=25), -42_000, "interest_charge",
              "LIQUIDACION DE INTERESES-COMISIONES-GASTOS")
        # loan instalment: labelled on even months, hidden in "-" on odd ones
        if index % 2 == 0:
            b.txn(main, month.replace(day=5), -465_000, "debt_repayment", "[COMPANY] [NUM]")
        else:
            b.lists["dash_installment"].append(
                b.txn(main, month.replace(day=5), -465_000, "-", "LIQU.PTMO. 0355 [NUM].051.1")
            )
        # credit line works as an operating account and is topped up from main
        for cents in _split(rng, 2_400_000, 3):
            b.txn(line, month.replace(day=rng.randint(2, 24)), -cents, "payment",
                  "PAGO FACTURA [NUM] [COMPANY]")
        b.mirror(main, line, month.replace(day=26), 2_300_000 + index * 100,
                 out_category="transfer", in_category="transfer")
        # intra-company sweep between the two current accounts
        out_category, in_category = labels[index % 3]
        b.mirror(main, second, month.replace(day=12), 1_500_000 + index * 1_000,
                 out_category=out_category, in_category=in_category, offset=offsets[index % 10])
        b.invoice_month(treasury, month, stamped=False, late_share=0.3, unpaid_share=0.1,
                        ticket=900_000, track=True)
    # two identical transfers on the same day: pairing must stay 1:1
    twin_day = date(2025, 10, 14)
    twin = b.reserve(main, twin_day, 777_700)
    for _ in range(2):
        b.mirror(main, second, twin_day, twin, ambiguous=True, reserve=False)
    b.lists["dash_drawdown"].append(
        b.txn(main, date(2025, 3, 18), 8_000_000, "-",
              "[ACCOUNT] ABONO POR DISPOSICION DE [COMPANY]/CREDITO")
    )
    b.txn(main, date(2025, 3, 18), -40_000, "-", "COMISION DISPOSICION [NUM]")
    # swept subsidiary: every active day ends at zero, cash goes to the treasury centre
    for index, month in enumerate(months):
        days = calendar.monthrange(month.year, month.month)[1]
        active = sorted(rng.sample(range(1, days), 8))
        for position, day_number in enumerate(active):
            day = month.replace(day=day_number)
            for cents in _split(rng, 600_000, 2):
                b.txn(swept_account, day, cents, "collection", "TRANSFERENCIA DE [COMPANY] FRA [NUM]")
            b.txn(swept_account, day, -rng.randint(20_000, 90_000), "payment", "PAGO FACTURA [NUM]")
            out_category, in_category = labels[(index + position) % 3]
            offset = 1 if position % 4 == 3 else 0
            b.mirror(swept_account, main, day, b.balance(swept_account, day),
                     out_category=out_category, in_category=in_category, offset=offset)
    for month in month_range(date(2025, 2, 1), LAST_MONTH):
        b.operating_month(late_account, month, 7_000_000, 6_400_000)
        b.invoice_month(late, month, stamped=False, late_share=0.2, unpaid_share=0.05, ticket=400_000)
    for product_id in (main, second, usd):
        b.txn(product_id, AS_OF, 150_000, "collection", "TRANSFERENCIA DE [COMPANY] FRA [NUM]")

    # G2: stamped invoice regime, no debt
    b.group("GROUP_0002", "Holded", 1)
    stamped = b.company("GROUP_0002", country="ES", erp="holded")
    stamped_account = b.bank_product(stamped, opening=9_000_000, bank="Caixabank Empresas", service="caixabank_emp")
    saving = b.bank_product(stamped, "saving", opening=12_000_000, bank="Caixabank Empresas", service="caixabank_emp")
    for month in months:
        b.operating_month(stamped_account, month, 5_000_000, 4_600_000)
        b.invoice_month(stamped, month, stamped=True, late_share=0.0, unpaid_share=0.05, ticket=250_000)
    b.txn(saving, date(2025, 1, 15), 35_000, "investment_return", "ABONO INTERESES [NUM]")

    # G3: no invoices, a loan, an account connected mid-window
    b.group("GROUP_0003", "", 1)
    bank_only = b.company("GROUP_0003")
    first_account = b.bank_product(bank_only, opening=3_500_000)
    mid_account = b.bank_product(bank_only, opening=1_000_000, bank="Bankinter Empresas",
                                 service="bankinter_emp", created=date(2025, 6, 9))
    b.debt_product(bank_only, "loan", granted=-12_000_000, outstanding=-7_400_000)
    for month in months:
        b.operating_month(first_account, month, 6_000_000, 5_700_000)
        b.txn(first_account, month.replace(day=7), -210_000, "debt_repayment", "[COMPANY] [NUM]")
        if month >= date(2025, 6, 1):
            b.operating_month(mid_account, month, 2_500_000, 2_200_000, payroll=False)

    # G4: fewer than six observed months, no invoices, no debt
    b.group("GROUP_0004", "", 1)
    short = b.company("GROUP_0004", created=date(2026, 4, 1))
    short_account = b.bank_product(short, opening=2_000_000, created=date(2026, 4, 1))
    for month in month_range(date(2026, 4, 1), LAST_MONTH):
        b.operating_month(short_account, month, 3_000_000, 2_800_000)

    # G5: deteriorating payer; sentinel balance, pending rows, quoted newline, HUF account
    b.group("GROUP_0005", "Microsoft Business Central", 2)
    weak = b.company("GROUP_0005", country="ES", erp="businessCentral")
    sibling = b.company("GROUP_0005", erp="businessCentral")
    weak_account = b.bank_product(weak, opening=5_000_000)
    sentinel = b.bank_product(weak, opening=100_000, bank="Other (customer-defined)", service="custom")
    sibling_account = b.bank_product(sibling, opening=4_000_000)
    huf = b.bank_product(sibling, currency="HUF", opening=900_000, bank="Revolut", service="revolut")
    b.bank_product(sibling, "card", opening=0)
    for index, month in enumerate(months):
        decay = 0.97 ** max(0, index - 15)
        b.operating_month(weak_account, month, int(9_000_000 * decay), 8_600_000)
        b.operating_month(sibling_account, month, 4_000_000, 3_700_000)
        b.txn(sentinel, month.replace(day=3), -15_000, "fee", "COMISION MANTENIMIENTO")
        b.txn(huf, month.replace(day=11), 450_000, "collection", "ATUTALAS [COMPANY] [NUM]")
        late_share = 0.15 if index < 16 else min(0.8, 0.15 + 0.08 * (index - 15))
        b.invoice_month(weak, month, stamped=False, late_share=late_share,
                        unpaid_share=0.05 if index < 16 else 0.2, ticket=500_000)
    b.single["newline"] = b.txn(
        weak_account, date(2026, 3, 30), -56_052, "interest_charge",
        "INTERESES DE [COMPANY]\nPTMO.:[NUM]               \n                    ",
    )
    b.txn(weak_account, date(2026, 4, 2), -120_000, "payment",
          'TRANSFERENCIA A [COMPANY], S.L. "PAGO FRA [NUM]"')
    for day, cents in ((date(2025, 11, 20), -2_500_000), (date(2026, 8, 28), 3_100_000),
                       (date(2026, 8, 31), -1_900_000), (AS_OF, 800_000)):
        b.lists["pending"].append(
            b.txn(weak_account, day, cents, "payment" if cents < 0 else "collection",
                  "PAGO PENDIENTE [NUM]", status="pending")
        )

    # G6: healthy single company, invoices, a guarantee as only debt product
    b.group("GROUP_0006", "Sage 200", 1)
    healthy = b.company("GROUP_0006", country="ES", erp="sage200")
    healthy_account = b.bank_product(healthy, opening=30_000_000)
    guarantee = b.debt_product(healthy, "guarantee", granted=-1, outstanding=-5_000_000)
    for month in months:
        b.operating_month(healthy_account, month, 12_000_000, 11_200_000)
        b.invoice_month(healthy, month, stamped=False, late_share=0.1, unpaid_share=0.02, ticket=700_000)
    # rows every as-of reader must ignore
    b.lists["ignored_invoices"] += [
        b.invoice(healthy, date(2026, 5, 4), date(2026, 6, 3), date(2026, 6, 3), 180_000,
                  document_type="paymentDocument"),
        b.invoice(healthy, date(2026, 5, 6), date(2026, 6, 5), date(2026, 6, 5), -60_000,
                  document_type="note"),
        b.invoice(healthy, date(2026, 5, 8), date(2026, 6, 7), date(2026, 6, 7), 95_000,
                  document_type="invoiceGroup"),
        b.invoice(healthy, date(2026, 5, 9), date(2026, 6, 8), date(2026, 6, 8), 210_000,
                  status="cancel", pending=0),
        b.invoice(healthy, date(2026, 5, 20), date(2026, 6, 19), date(2026, 5, 2), 130_000),
    ]
    # partial payment and a future expected date: open, never settled
    b.invoice(healthy, date(2026, 6, 2), date(2026, 7, 2), date(2026, 7, 2), 400_000,
              status="payment_in_progress", pending=150_000)
    b.invoice(treasury, date(2026, 7, 24), date(2026, 9, 22), None, -25_235, currency="USD")

    b.single.update(
        usd=usd, usd_company=treasury, huf=huf, line=line, loan=loan, guarantee=guarantee,
        sentinel=sentinel, own_date=saving, late=late, mid_account=mid_account,
        mid_company=bank_only, swept=swept, treasury=treasury, stamped=stamped, weak=weak,
        short=short,
    )


def _extra_group(b: _Builder, number: int) -> None:
    rng = b.rng
    group_id = f"GROUP_{number:04d}"
    size = rng.choice([1, 1, 2])
    erp = rng.choice(["", "", "netsuite", "businessCentral"])
    b.group(group_id, erp, size)
    for _ in range(size):
        company_id = b.company(group_id, erp=erp)
        first = month_add(FIRST_MONTH, rng.choice([0, 0, 0, 4, 9]))
        account = b.bank_product(company_id, opening=rng.randint(1_000_000, 20_000_000))
        inflow = rng.randint(2_000_000, 15_000_000)
        has_debt = rng.random() < 0.4
        if has_debt:
            b.debt_product(company_id, "loan", granted=-10_000_000, outstanding=-6_000_000)
        for month in month_range(first, LAST_MONTH):
            b.operating_month(account, month, inflow, int(inflow * rng.uniform(0.85, 1.05)))
            if has_debt:
                b.txn(account, month.replace(day=6), -150_000, "debt_repayment", "[COMPANY] [NUM]")
            if erp:
                b.invoice_month(company_id, month, stamped=False, late_share=0.2,
                                unpaid_share=0.05, ticket=300_000)


def make_dataset(path: Path, n_groups: int = 6, seed: int = 7) -> SyntheticDataset:
    """Writes the eight CSVs under ``path`` and returns ids the tests assert on.

    The first six groups are fixed archetypes; further groups are generic.
    """
    if n_groups < 6:
        raise ValueError("make_dataset needs n_groups >= 6: the first six are the archetypes")
    b = _Builder(seed)
    _core_groups(b)
    for number in range(7, n_groups + 1):
        _extra_group(b, number)
    b.finish_balances(own_date_product=b.single["own_date"], sentinel_product=b.single["sentinel"])
    counts = b.write(Path(path))

    product_first: dict[str, date] = {}
    company_first: dict[str, date] = {}
    balances: dict[tuple[str, date], int] = {}
    for product_id, entries in b.ledger.items():
        first = min(day for day, _ in entries).replace(day=1)
        product_first[product_id] = first
        company_id = b.product_company[product_id]
        company_first[company_id] = min(first, company_first.get(company_id, first))
        for month in month_range(first, LAST_MONTH):
            balances[(product_id, month)] = b.balance(product_id, month_end(month))
    by_group: dict[str, list[str]] = defaultdict(list)
    for company_id, group_id in b.company_group.items():
        by_group[group_id].append(company_id)
    single = b.single
    return SyntheticDataset(
        path=Path(path), seed=seed, first_month=FIRST_MONTH, last_month=LAST_MONTH, as_of=AS_OF,
        group_ids=tuple(by_group), company_ids=tuple(b.company_group),
        companies_by_group={key: tuple(value) for key, value in by_group.items()},
        company_first_month=company_first, product_first_month=product_first, row_counts=counts,
        mirror_pairs=tuple(b.lists["mirror_pairs"]),
        dash_installment_ids=tuple(b.lists["dash_installment"]),
        dash_drawdown_ids=tuple(b.lists["dash_drawdown"]),
        dash_unrecoverable_ids=tuple(b.lists["dash_unrecoverable"]),
        newline_transaction_id=single["newline"],
        pending_transaction_ids=tuple(b.lists["pending"]),
        blank_status_transaction_ids=tuple(b.lists["blank_status"]),
        usd_product_id=single["usd"], usd_company_id=single["usd_company"],
        fx_excluded_product_id=single["huf"],
        credit_line_product_id=single["line"], credit_line_company_id=single["treasury"],
        credit_line_granted_cents=30_000_000, credit_line_drawn_cents=12_000_000,
        loan_product_id=single["loan"], guarantee_product_id=single["guarantee"],
        sentinel_product_id=single["sentinel"], own_date_anchor_product_id=single["own_date"],
        late_member_company_id=single["late"], late_member_group_id="GROUP_0001",
        late_member_first_month=date(2025, 2, 1),
        mid_window_product_id=single["mid_account"], mid_window_company_id=single["mid_company"],
        mid_window_first_month=date(2025, 6, 1),
        swept_company_id=single["swept"], treasury_company_id=single["treasury"],
        stamped_company_id=single["stamped"], non_stamped_company_id=single["treasury"],
        deteriorating_company_id=single["weak"],
        late_ap_invoice_ids=tuple(b.lists["late_ap"]),
        unpaid_ap_invoice_ids=tuple(b.lists["unpaid_ap"]),
        late_ar_invoice_ids=tuple(b.lists["late_ar"]),
        unpaid_ar_invoice_ids=tuple(b.lists["unpaid_ar"]),
        ignored_invoice_ids=tuple(b.lists["ignored_invoices"]),
        no_invoice_group_id="GROUP_0003", no_debt_group_id="GROUP_0002",
        short_history_company_id=single["short"], short_history_group_id="GROUP_0004",
        month_end_balance_cents=balances,
    )


# --------------------------------------------------------------------------
# dataset transforms (file level, stdlib csv)
# --------------------------------------------------------------------------


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _write(path: Path, name: str, rows: list[dict[str, str]]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with (path / name).open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=HEADERS[name], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def filter_dataset(source: Path, target: Path, group_ids: set[str] | list[str]) -> Path:
    """Copy of the dataset holding only ``group_ids`` (every file filtered)."""
    keep = set(group_ids)
    companies = [row for row in _read(source / "companies.csv") if row["group_id"] in keep]
    members = {row["company_id"] for row in companies}
    for name in HEADERS:
        if name == "groups.csv":
            rows = [row for row in _read(source / name) if row["group_id"] in keep]
        elif name == "companies.csv":
            rows = companies
        else:
            rows = [row for row in _read(source / name) if row["company_id"] in members]
        _write(target, name, rows)
    return target


def truncate_dataset(source: Path, target: Path, last_month: date) -> Path:
    """The dataset as it would have been extracted at the end of ``last_month``.

    Transactions and invoices after the cut are removed, invoices settled later
    are re-opened, balances are rolled back in integer cents and dated at the
    cut (sentinels untouched). Master data and debt stock stay as declared.
    """
    cut = month_end(last_month)
    transactions = _read(source / "transactions.csv")
    kept = [row for row in transactions if date.fromisoformat(row["date"][:10]) <= cut]
    invoices = []
    for row in _read(source / "invoices.csv"):
        if date.fromisoformat(row["issuance_date"][:10]) > cut:
            continue
        paid = date.fromisoformat(row["payment_date"][:10])
        due = date.fromisoformat(row["due_date"][:10])
        if row["status"] == "paid" and paid > cut:
            row = dict(row, status="overdue" if due <= cut else "pending",
                       pending_amount=row["amount"], payment_date=row["due_date"])
        invoices.append(row)
    balances = []
    for row in _read(source / "balances.csv"):
        cents = to_cents(row["balance"])
        anchor = date.fromisoformat(row["date"][:10])
        if abs(cents) < SENTINEL_ABS_CENTS and anchor > cut:
            moved = sum(
                to_cents(item["amount"]) for item in transactions
                if item["product_id"] == row["product_id"] and item["status"] != "pending"
                and cut < date.fromisoformat(item["date"][:10]) <= anchor
            )
            row = dict(row, balance=money(cents - moved), date=_stamp(cut))
            for column in ("liquidity", "countable"):
                if row[column]:
                    row[column] = money(to_cents(row[column]) - moved)
        balances.append(row)
    for name in HEADERS:
        rows = {"transactions.csv": kept, "invoices.csv": invoices, "balances.csv": balances}.get(name)
        _write(target, name, rows if rows is not None else _read(source / name))
    return target


def scale_dataset(source: Path, target: Path, factor: int) -> Path:
    """Every money column multiplied by the integer ``factor`` (sentinels untouched)."""
    for name in HEADERS:
        rows = _read(source / name)
        for row in rows:
            for column in MONEY_COLUMNS.get(name, []):
                if row[column] and abs(to_cents(row[column])) < SENTINEL_ABS_CENTS:
                    row[column] = money(to_cents(row[column]) * factor)
        _write(target, name, rows)
    return target


def shuffle_dataset(source: Path, target: Path, seed: int = 1) -> Path:
    """Same records, different physical row order in every file."""
    rng = random.Random(seed)
    for name in HEADERS:
        rows = _read(source / name)
        rng.shuffle(rows)
        _write(target, name, rows)
    return target


# --------------------------------------------------------------------------
# random panel rows (pure-core property tests)
# --------------------------------------------------------------------------


def random_panel_row(rng: random.Random, **overrides: object) -> PanelRow:
    """A plausible entity-month covering every branch: with and without cash
    anchor, invoices, debt, lines, history, live feed and perimeter changes."""
    size = 10 ** rng.uniform(3, 7)
    months_observed = rng.choice([1, 3, 5, 6, 7, 9, 12, 18, 24])
    outflow = size * rng.uniform(0.5, 1.5)
    inflow = outflow * rng.uniform(0.5, 1.5)
    has_cash = rng.random() < 0.9
    has_lines = rng.random() < 0.4
    has_debt = has_lines or rng.random() < 0.3
    has_invoices = rng.random() < 0.7
    granted = size * rng.uniform(0.5, 3) if has_lines else 0.0
    drawn = granted * rng.choice([0.0, rng.random(), 0.99, 1.0]) if has_lines else 0.0
    cash = size * rng.uniform(-0.5, 4) if has_cash else None
    base_rows = rng.uniform(20, 400)
    known = min(12, months_observed)
    series = [None] * (12 - known) + [inflow * rng.uniform(0.3, 1.7) for _ in range(known)]
    changed = rng.random() < 0.15
    values: dict[str, object] = {
        "entity_kind": rng.choice(["group", "company"]),
        "entity_id": "ENTITY_X",
        "group_id": "GROUP_X",
        "month": date(2026, rng.randint(1, 8), 1),
        "months_observed": months_observed,
        "months_active_12m": known,
        "n_members": rng.randint(1, 5),
        "n_products": rng.randint(1, 12),
        "perimeter_changed": changed,
        "members_joined": int(changed),
        "products_connected": int(changed),
        "months_since_perimeter_change": 0 if changed else rng.choice([None, 1, 2, 3, 9]),
        "rows_month": int(base_rows * rng.uniform(0.2, 1.5)),
        "rows_3m": int(3 * base_rows * rng.choice([0.2, 0.5, 0.9, 1.0, 1.3])),
        "rows_base_median": base_rows if months_observed >= 7 else None,
        "rows_base_months": max(0, min(9, months_observed - 3)),
        "cash_month_end": cash,
        "cash_intra_month_min": cash - size * rng.uniform(0, 1) if has_cash else None,
        "n_cash_products": rng.randint(1, 6) if has_cash else 0,
        "cash_anchor_coverage": rng.choice([1.0, 1.0, 0.5]) if has_cash else None,
        "granted": granted,
        "drawn": drawn,
        "headroom": max(0.0, granted - drawn),
        "n_credit_lines": int(has_lines),
        "neg_liquidity_months_6m": rng.choice([0, 0, 0, 1, 3, 6]),
        "swept_subsidiary": rng.random() < 0.1,
        "cash_share_of_group": rng.random(),
        "zero_balance_account_share": rng.random(),
        "sweep_pairs_12m": rng.randint(0, 40),
        "op_inflow_1m": inflow,
        "op_outflow_1m": outflow,
        "op_inflow_3m": inflow * 3,
        "op_outflow_3m": outflow * 3,
        "op_outflow_median_3m": rng.choice([outflow, outflow, outflow, 0.0, None]),
        "op_inflow_12m": inflow * known,
        "op_outflow_12m": outflow * known,
        "lfl_op_inflow_12m": tuple(series),
        "intragroup_in": size * rng.random(),
        "intragroup_out": size * rng.random(),
        "mirror_netted_1m": size * rng.random(),
        "n_debt_products": rng.randint(1, 5) if has_debt else 0,
        "debt_outstanding": size * rng.uniform(0, 10) if has_debt else 0.0,
        "debt_service_12m": outflow * rng.uniform(0.01, 2) if has_debt else 0.0,
        "interest_12m": outflow * rng.uniform(0, 0.01) if has_debt else 0.0,
        "debt_rollover_netted_12m": 0.0,
        "debt_drawdowns_12m": size * rng.random() if has_debt else 0.0,
        "has_invoices": has_invoices,
        "invoice_months_observed": rng.choice([1, 2, 6, 24]) if has_invoices else 0,
        "uncategorised_share": rng.choice([0.0, 0.1, 0.5, 0.9]),
        "fx_excluded_share": rng.choice([0.0, 0.0, 0.3]),
        "sentinel_balances_dropped": rng.choice([0, 0, 1]),
    }
    for side in ("ap", "ar"):
        scorable = has_invoices and rng.random() < 0.8
        count = rng.choice([1, 8, 40]) if scorable else 0
        values.update(
            {
                f"{side}_cohort_n": count,
                f"{side}_cohort_amount": size * rng.random() if count else 0.0,
                f"{side}_days_beyond_terms": rng.uniform(-30, 120) if count else None,
                f"{side}_unpaid30_share": rng.random() if count else None,
                f"{side}_settlements_6m": rng.choice([0, 5, 10, 60]) if has_invoices else 0,
                f"{side}_stamped_share": rng.choice([0.0, 0.2, 0.9]) if has_invoices else None,
                f"{side}_open": size * rng.random() if has_invoices else 0.0,
                f"{side}_overdue": size * rng.random() * 0.3 if has_invoices else 0.0,
            }
        )
    values.update(overrides)
    names = {item.name for item in fields(PanelRow)}
    assert set(values) == names, sorted(names ^ set(values))
    return PanelRow(**values)


def scale_row(row: PanelRow, factor: float) -> PanelRow:
    """Every EUR column multiplied by ``factor``; counts, shares and days untouched."""
    changes: dict[str, object] = {}
    for name, unit in PANEL_UNITS.items():
        if unit != "EUR":
            continue
        value = getattr(row, name)
        if isinstance(value, tuple):
            changes[name] = tuple(None if item is None else item * factor for item in value)
        elif value is not None:
            changes[name] = value * factor
    return replace(row, **changes)


# --------------------------------------------------------------------------
# frame comparison
# --------------------------------------------------------------------------


def _same(left: object, right: object, tol: float, where: str) -> None:
    if isinstance(left, float) and isinstance(right, float):
        assert abs(left - right) <= tol, f"{where}: {left!r} != {right!r}"
    elif isinstance(left, dict) and isinstance(right, dict):
        assert left.keys() == right.keys(), f"{where}: keys differ"
        for key in left:
            _same(left[key], right[key], tol, f"{where}.{key}")
    elif isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        assert len(left) == len(right), f"{where}: lengths differ"
        for index, (one, other) in enumerate(zip(left, right)):
            _same(one, other, tol, f"{where}[{index}]")
    else:
        assert left == right, f"{where}: {left!r} != {right!r}"


def assert_same_frames(left, right, *, keys, tol: float = 1e-9, ignore=()) -> None:
    """Same rows by ``keys``: numerics within ``tol`` (nested values included),
    everything else equal. ``ignore`` lists columns left out."""
    left = left.drop([name for name in ignore if name in left.columns]).sort(keys)
    right = right.drop([name for name in ignore if name in right.columns]).sort(keys)
    assert left.columns == right.columns
    assert left.height == right.height, f"{left.height} rows != {right.height} rows"
    assert left.select(keys).equals(right.select(keys)), "entity-months differ"
    for index, (one, other) in enumerate(zip(left.to_dicts(), right.to_dicts())):
        _same(one, other, tol, f"row {index} {[one[key] for key in keys]}")


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def datasets() -> SimpleNamespace:
    """Dataset tools: make, filter, truncate, scale, shuffle."""
    return SimpleNamespace(
        make=make_dataset, filter=filter_dataset, truncate=truncate_dataset,
        scale=scale_dataset, shuffle=shuffle_dataset, headers=HEADERS,
        month_add=month_add, month_end=month_end, to_cents=to_cents,
    )


@pytest.fixture(scope="session")
def panel_rows() -> SimpleNamespace:
    """Pure-core tools: random (rng, **overrides) and scale (row, factor)."""
    return SimpleNamespace(random=random_panel_row, scale=scale_row)


@pytest.fixture(scope="session")
def same_frames():
    """assert_same_frames(left, right, *, keys, tol=1e-9, ignore=())."""
    return assert_same_frames


@pytest.fixture(scope="session")
def synthetic(tmp_path_factory: pytest.TempPathFactory) -> SyntheticDataset:
    return make_dataset(tmp_path_factory.mktemp("synthetic"), n_groups=6, seed=7)


@pytest.fixture(scope="session")
def params() -> Params:
    return load_params()


@pytest.fixture(scope="session")
def real_data_dir() -> Path:
    path = _real_data_dir()
    if path is None:
        pytest.skip("XRAY_DATA does not point to a dataset folder")
    return path
