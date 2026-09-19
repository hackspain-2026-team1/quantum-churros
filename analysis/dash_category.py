"""Category '-': why the sign is the default and which narrative rules may override it.

Usage: python3 analysis/dash_category.py --data <dir> [--params params/reference_v1.json]

About a quarter of the bank rows carry category '-'. Three measurements on booked
in-window rows, EUR by static FX on the account currency:

1. **Sign default**: on the rows that DO have a category, how often does the sign
   alone give the right class? Two readings: the engine classes (amount > 0 ->
   operating inflow; amount < 0 -> operating outflow or debt service) and the wide
   families first measured (inflow also investment_return and collection_refund;
   outflow also withdrawals, investment_deployment and payment_refund).
2. **Narrative rules**: for each rule, precision = share of labelled rows matching
   the pattern whose category is the rule's label (an upper bound: '-' rows are the
   ones the categoriser failed on), and coverage = '-' rows and EUR the rule claims
   when the rules run in order, first match wins. ``pattern only`` ignores the sign
   and veto conditions, which is how coverage was first measured.
3. **Retention adjustments**: '-' rows whose narrative is an account-hold adjustment,
   split into the hold templates proper and every other narrative with RETENCION.

Rules are matched case-insensitively on the description with newlines as spaces; a
rule may require a sign and may carry a veto pattern. ``--params`` measures the rule
table shipped in the engine parameters instead of the built-in copy.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter

from _common import DEBT_SERVICE, OP_IN, OP_OUT, booked_transactions, load_products, parse_args, pct, report, to_eur

WIDE_IN = OP_IN | {"investment_return", "collection_refund"}
WIDE_OUT = OP_OUT | DEBT_SERVICE | {"cash_withdrawal", "pos_withdrawal", "investment_deployment", "payment_refund"}
HOLD_TEMPLATES = re.compile(r"AP\.RET\.DST|(QUITAR|AJUSTE) RETENCI[OÓ]N", re.I)

UTILITIES = (
    "IBERDROLA|ENDESA|NATURGY|REPSOL|CEPSA|TELEF[OÓ]NICA|MOVISTAR|VODAFONE|ORANGE|MASMOVIL|HOLALUZ|"
    "TOTALENERGIES|CANAL DE ISABEL|AGUAS DE|AIG[UÜ]ES"
)
# (id, pattern, veto, sign, label): the retention rule plus the 11 validated overrides
RULES = [
    ("retention_adjustment", r"RETENCI[OÓ]N|AP\.RET\.DST", None, "any", "balance_adjustment"),
    ("scf_balance_adjustment", r"SCF-AJUS\.? ?SALDO", None, "any", "transfer"),
    ("payout", r"\bPAYOUT\b", None, "any", "transfer"),
    ("amortisation_charge", r"CARGO POR AMORTIZACI[OÓ]N", None, "negative", "debt_repayment"),
    ("loan_instalment", r"LIQUID\.? ?CUOTA PTMO", None, "negative", "debt_repayment"),
    ("amortisation", r"AMORTIZ", r"COMISI[OÓ]N", "negative", "debt_repayment"),
    ("social_security", r"\bTGSS\b|SEG(UROS|URIDAD)?\.? ?SOCIAL(ES)?", None, "negative", "social_security"),
    ("tax_agency", r"\bAEAT\b", r"DEVOLUCI", "negative", "tax"),
    ("utility", UTILITIES, None, "negative", "utility"),
    ("fee", r"\bFEES?\b", None, "negative", "fee"),
    ("commission", r"COMISI[OÓ]N", None, "negative", "fee"),
    ("sepa_overboeking", r"SEPA OVERBOEKING", None, "positive", "collection"),
]
# precision first measured per pattern, without the sign and veto conditions (labelled rows)
FIRST_MEASURED = {
    "scf_balance_adjustment": "0.987 (1,876)",
    "payout": "0.941 (3,564)",
    "amortisation_charge": "1.000 (1,686)",
    "loan_instalment": "1.000 (1,167)",
    "amortisation": "0.829",
    "social_security": "0.987 (21,371)",
    "tax_agency": "0.831",
    "utility": "0.901 (10,486)",
    "fee": "0.929 (30,717)",
    "commission": "0.852 (113,067)",
    "sepa_overboeking": "0.956 (3,761)",
}


def load_rules(path: str | None):
    if not path:
        return RULES
    with open(path, encoding="utf-8") as handle:
        table = json.load(handle)["dash_rules"]
    return [(r["id"], r["pattern"], r.get("exclude"), r.get("sign", "any"), r.get("label")) for r in table]


def main() -> None:
    args = parse_args(
        __doc__.splitlines()[0], params={"default": None, "help": "engine parameter file with a dash_rules table"}
    )
    started = time.time()
    products = load_products(args.data)
    rules = [
        (rule_id, re.compile(pattern, re.I), re.compile(veto, re.I) if veto else None, sign, label)
        for rule_id, pattern, veto, sign, label in load_rules(args.params)
    ]
    any_rule = re.compile("|".join(f"(?:{r[1].pattern})" for r in rules), re.I)
    retention_ids = {r[0] for r in rules if r[4] == "balance_adjustment"}
    override_ids = [r[0] for r in rules if r[0] not in retention_ids]

    def matches(rule, text, amount):
        _id, pattern, veto, sign, _label = rule
        if (sign == "negative" and amount >= 0) or (sign == "positive" and amount <= 0):
            return False
        return bool(pattern.search(text)) and not (veto and veto.search(text))

    sign_hits, sign_rows, held = Counter(), Counter(), Counter()
    pattern_only_rows = pattern_only_eur = 0
    labelled = {r[0]: Counter() for r in rules}  # rule -> category counts on labelled rows
    claimed_rows, claimed_eur = Counter(), Counter()
    dash_rows = dash_eur = dash_no_fx = 0
    dash_sign = Counter()
    for _company, product, _day, _month, amount, category, description in booked_transactions(args.data, "description"):
        text = description.replace("\n", " ").replace("\r", " ")
        hit = any_rule.search(text) is not None
        if category != "-":
            if amount > 0:
                sign_rows["inflow"] += 1
                sign_hits["inflow"] += category in OP_IN
                sign_hits["inflow_wide"] += category in WIDE_IN
                sign_hits["inflow_transfer"] += category == "transfer"
            elif amount < 0:
                sign_rows["outflow"] += 1
                sign_hits["outflow"] += category in OP_OUT or category in DEBT_SERVICE
                sign_hits["outflow_wide"] += category in WIDE_OUT
                sign_hits["outflow_transfer"] += category == "transfer"
            if hit:
                for rule in rules:
                    if matches(rule, text, amount):
                        labelled[rule[0]][category] += 1
            continue
        info = products.get(product)
        value = to_eur(abs(amount), info[2] if info else None)
        dash_rows += 1
        dash_eur += value or 0.0
        dash_no_fx += value is None
        winner = next((rule[0] for rule in rules if matches(rule, text, amount)), None) if hit else None
        if winner is None:
            dash_sign["inflow" if amount > 0 else "outflow" if amount < 0 else "zero"] += 1
        else:
            claimed_rows[winner] += 1
            claimed_eur[winner] += value or 0.0
        if winner in retention_ids:
            kind = "hold_templates" if HOLD_TEMPLATES.search(text) else "other_retencion"
            held[kind + "_rows"] += 1
            held[kind + "_eur"] += value or 0.0
        elif hit and any(r[1].search(text) for r in rules if r[0] not in retention_ids):
            pattern_only_rows += 1
            pattern_only_eur += value or 0.0

    per_rule = {}
    for rule_id, _pattern, _veto, sign, label in rules:
        seen = labelled[rule_id]
        support = sum(seen.values())
        top = seen.most_common(1)[0] if seen else (None, 0)
        per_rule[rule_id] = {
            "label": label,
            "sign": sign,
            "labelled_rows_matching": support,
            "precision": round(seen[label] / support, 3) if support and label in seen else None,
            "dominant_category": top[0],
            "dominant_share": round(top[1] / support, 3) if support else None,
            "dash_rows_claimed": claimed_rows[rule_id],
            "dash_eur_m_claimed": round(claimed_eur[rule_id] / 1e6, 1),
        }
    result = {
        "rule_table": args.params or "built-in",
        "sign_default": {
            "inflow_rows": sign_rows["inflow"],
            "inflow_in_collection_family": sign_hits["inflow"],
            "precision_inflow": round(sign_hits["inflow"] / sign_rows["inflow"], 3),
            "outflow_rows": sign_rows["outflow"],
            "outflow_in_payment_family": sign_hits["outflow"],
            "precision_outflow": round(sign_hits["outflow"] / sign_rows["outflow"], 3),
            "inflow_in_wide_family": sign_hits["inflow_wide"],
            "precision_inflow_wide": round(sign_hits["inflow_wide"] / sign_rows["inflow"], 3),
            "outflow_in_wide_family": sign_hits["outflow_wide"],
            "precision_outflow_wide": round(sign_hits["outflow_wide"] / sign_rows["outflow"], 3),
            "pct_inflow_rows_labelled_transfer": pct(sign_hits["inflow_transfer"], sign_rows["inflow"], 1),
            "pct_outflow_rows_labelled_transfer": pct(sign_hits["outflow_transfer"], sign_rows["outflow"], 1),
        },
        "dash": {"rows": dash_rows, "eur_bn": round(dash_eur / 1e9, 3), "rows_without_fx": dash_no_fx},
        "override_rules_coverage": {
            "rows": sum(claimed_rows[i] for i in override_ids),
            "pct_of_dash_rows": pct(sum(claimed_rows[i] for i in override_ids), dash_rows),
            "eur_bn": round(sum(claimed_eur[i] for i in override_ids) / 1e9, 3),
            "pct_of_dash_value": pct(sum(claimed_eur[i] for i in override_ids), dash_eur),
            "pattern_only_rows": pattern_only_rows,
            "pattern_only_pct_of_dash_rows": pct(pattern_only_rows, dash_rows),
            "pattern_only_eur_bn": round(pattern_only_eur / 1e9, 3),
            "pattern_only_pct_of_dash_value": pct(pattern_only_eur, dash_eur),
        },
        "retention_adjustments": {
            "rows": sum(claimed_rows[i] for i in retention_ids),
            "pct_of_dash_rows": pct(sum(claimed_rows[i] for i in retention_ids), dash_rows, 3),
            "pct_of_dash_value": pct(sum(claimed_eur[i] for i in retention_ids), dash_eur, 1),
            "hold_template_rows": held["hold_templates_rows"],
            "hold_template_pct_of_dash_value": pct(held["hold_templates_eur"], dash_eur, 1),
            "other_retencion_rows": held["other_retencion_rows"],
            "other_retencion_eur_m": round(held["other_retencion_eur"] / 1e6, 1),
        },
        "dash_rows_left_to_the_sign": dict(dash_sign),
        "rules": per_rule,
    }
    s, cover, kept = result["sign_default"], result["override_rules_coverage"], result["retention_adjustments"]
    table = [
        ("metric", "measured", "validated"),
        (
            "labelled inflow rows that are operating inflow",
            f"{s['inflow_in_collection_family']} / {s['inflow_rows']} = {s['precision_inflow']}",
            "",
        ),
        (
            "  ... in the wide collection family",
            f"{s['inflow_in_wide_family']} / {s['inflow_rows']} = {s['precision_inflow_wide']}",
            "728,843 / 822,565 = 0.886",
        ),
        (
            "labelled outflow rows that are operating outflow or debt service",
            f"{s['outflow_in_payment_family']} / {s['outflow_rows']} = {s['precision_outflow']}",
            "",
        ),
        (
            "  ... in the wide payment family",
            f"{s['outflow_in_wide_family']} / {s['outflow_rows']} = {s['precision_outflow_wide']}",
            "1,014,203 / 1,087,313 = 0.933",
        ),
        (
            "labelled rows that are transfers: % of inflow / outflow rows",
            f"{s['pct_inflow_rows_labelled_transfer']} / {s['pct_outflow_rows_labelled_transfer']}",
            "",
        ),
        ("'-' rows / EUR bn", f"{dash_rows} / {result['dash']['eur_bn']}", "630,628 / 21.802"),
        (
            "override rules as shipped: '-' rows claimed (% of rows)",
            f"{cover['rows']} ({cover['pct_of_dash_rows']}%)",
            "",
        ),
        (
            "override rules as shipped: EUR bn claimed (% of value)",
            f"{cover['eur_bn']} ({cover['pct_of_dash_value']}%)",
            "",
        ),
        (
            "  pattern only: rows (%), EUR bn (%)",
            f"{cover['pattern_only_rows']} ({cover['pattern_only_pct_of_dash_rows']}%), "
            f"{cover['pattern_only_eur_bn']} ({cover['pattern_only_pct_of_dash_value']}%)",
            "35.3k (5.6%), 1.77 (8.1%)",
        ),
        ("retention rule: rows, % of '-' value", f"{kept['rows']}, {kept['pct_of_dash_value']}%", ""),
        (
            "  hold templates: rows, % of '-' value",
            f"{kept['hold_template_rows']}, {kept['hold_template_pct_of_dash_value']}%",
            "406, 35.0%",
        ),
        (
            "  other RETENCION narratives: rows, EUR m",
            f"{kept['other_retencion_rows']}, {kept['other_retencion_eur_m']}",
            "",
        ),
        ("rule: label, precision on labelled rows (n), '-' rows claimed", "", "pattern only"),
    ]
    for rule_id, line in per_rule.items():
        measured = (
            f"{line['label']}, {line['precision']} ({line['labelled_rows_matching']}), {line['dash_rows_claimed']}"
        )
        if line["precision"] is None:
            measured = (
                f"{line['label']}; labelled rows land on {line['dominant_category']} {line['dominant_share']} "
                f"({line['labelled_rows_matching']}), {line['dash_rows_claimed']}"
            )
        table.append((f"  {rule_id}", measured, FIRST_MEASURED.get(rule_id, "")))
    report("dash_category", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
