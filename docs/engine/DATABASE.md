# Database flow

PostgreSQL is a first-class source and sink of the engine. Nothing shown by the
product is typed by hand: every figure is measured from the ingested dataset.

```
8 CSVs ──make db-seed──▶ source.*  ──xray-score predict <postgres url>──▶ artifacts (parquet, CSV, bundle)
                                                                              │
                                   xray.*  ◀──────────make db-publish────────┘
```

| Step | Command | Result |
|---|---|---|
| Start | `make up` | PostgreSQL (host port 5433 by default; override with `POSTGRES_PORT`), API, web |
| Ingest | `make db-seed` | `source.<table>`: the eight files untouched, keyed by `dataset_hash` (sha256 of the files). NUL bytes inside descriptions are removed, PostgreSQL text cannot hold them |
| Score from the database | `make predict XRAY_DATA=postgresql://xray:xray-local@localhost:5433/xray` | Same outputs as scoring the folder |
| Publish | `make db-publish XRAY_OUT=artifacts/full` | `xray.entity_month_panel`, `xray.entity_month_score`, `xray.alert` |

## Same numbers from both sources

`io.load_source` takes a folder or a PostgreSQL URL. The database rows go through
the same typing step as the files (`_read_csv` → `_to_cache`), and both sources
share one `dataset_hash`. Measured on the full dataset: the eight tables are
equal frame by frame (2,549,858 booked transactions, 897,894 invoices) and
`scores`, `panel` (77 columns) and `alerts` are identical.
`backend/tests/test_db_source.py` repeats the comparison when
`XRAY_TEST_SOURCE_DATABASE_URL` and `XRAY_DATA` are set.

The folder path stays the default so a cold folder scores with one command and
no services.

## Published tables

One row per entity-month, one attribute per column (layout in
`backend/app/engine_tables.py`, generated from the engine parquet schemas; the
publisher refuses a drifted schema).

- `xray.entity_month_panel`: the 77 measured attributes (perimeter, cash,
  headroom, flows, days beyond terms, debt service, size band, feed state).
- `xray.entity_month_score`: score, band, base, penalty, cap, confidence,
  abstention, and the pillar structs flattened (`pillars_liquidity`,
  `contributions_payments`, `series_buffer_days`, ...). Nested values
  (`drivers`, `trajectory`, `gates`, `flags`, `caps_fired`) are JSONB.
- `xray.alert`: the alert stream with its suppression reason.

Publishing is idempotent per `dataset_hash`: the dataset's rows are replaced in
one transaction.

```sql
SELECT band, count(*), round(avg(score)::numeric, 1)
FROM xray.entity_month_score
WHERE entity_kind = 'group' AND month = '2026-08-01'
GROUP BY 1;
```

The API reads company debt products from `source.debt_products` of the most
recent completed import. Migrations never carry scores: revision `20260918_02`
is a no-op and `20260919_07` clears the rows it used to insert.
