# Aadarsh's /analyze reference handoff

[PROVISIONAL] REF-01: owner Aadarsh with Adrian, confirm at H9. This internal test-file layout does not change any public response field or enum.

Deliver `data/processed/trend_results_reference.json` with:

- data_status: real
- data_version: the exact processed export version (not a mock marker)
- contract_version: the exact contract version
- cases: nonempty list of objects, each with request (the AnalyzeRequest body) and result (the complete frozen TrendResult, including Evidence).

Use genuine Group 3 outputs. Do not relabel mock results. JSON must have all scientific fields, timezone-aware computed_at, and normal nulls rather than sentinels. Example structure below is a format illustration; angle-bracket values are instructions, not a valid scientific reference file:

```text
{
  "data_status": "real",
  "data_version": "<actual Group 3 export version>",
  "contract_version": "1.0",
  "cases": [
    {"request": {"region_id":"IGP","variable":"aod","start":"2003-01","end":"2024-12","season":"all"},
     "result": <full Group 3 TrendResult object>}
  ]
}
```

Run `python -m pytest backend/tests/test_adrian_reference.py` after the package and processed files arrive. The integration check skips only if the named reference file is absent. Once present, missing real inputs/package or invalid/mismatched reference data cause failure, not a skip or mock fallback. Production store startup and version pin checks still apply.

The test compares every scientific/selection field with absolute numeric tolerance 1e-6 (relative tolerance zero). Null stays null, booleans are not treated as numbers, lists preserve order, and key sets must agree. Only computed_at is excluded from equality because a fresh computation can have a different timestamp; its timezone format is still validated by TrendResult.
