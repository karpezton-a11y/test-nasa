# Sritharan — observed research package

Open START_HERE.txt and presentation/Sritharan_Observed_Research.pptx first. The presentation contains real 2003–2024 findings, maps, NASA images, editable charts and methods. Read docs/research_findings.md for the full narrative and limitations.

Twelve original NASA Giovanni exports are included in data/raw: eight primary monthly/daily regional series, and four monthly Terra/MERRA-2 comparison series. results/ contains the processed data, actual dated anomaly flags, annual and seasonal rainfall indicators, QC, provenance, charts and descriptive comparisons. No synthetic fixtures enter these results.

## Reproduce

Use Python 3.12 or later and install requirements.txt. From this folder run:

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python run_pipeline.py --manifest inputs.json --output results --figures
python -m analysis.research_summary --results results
```

The manifest now points to actual files with their exact headers, units, fill values, selected boxes and NASA reproduction URLs. Originals remain intact and SHA256 hashes are recorded. inputs_template.json is only a template for future acquisitions.

## Source filtering

results/timeseries_monthly.csv contains 2,112 rows including supplementary comparison sources. results/timeseries_monthly_primary.csv contains only the four primary series (1,056 rows). results/timeseries_monthly_comparison.csv contains the four comparison series. results/timeseries_daily.csv contains 32,144 rows. Filter source_id explicitly; never merge platforms into one unlabeled series.

## Aadarsh handoff

The data and M1 methods are ready for independent review. Send presentation/message_to_aadarsh.txt with the package. Aadarsh still owns trend, confidence/evidence, interaction and statistical validation Part B. His supplied PDF describes methods but contains no executable function implementation. With an actual adapter defining analyze_series(series, metadata), run:

```text
python run_reference.py --series results/timeseries_monthly_primary.csv --adapter path/to/aadarsh_adapter.py
```

No validated trend or interaction result is claimed. Review baseline decisions, negative daily AOD, spatial coverage and daily/monthly rainfall discrepancies before final interpretation. The working-app demonstration and final competition submission require the team’s app and Aadarsh’s statistical contribution.

## Credits

NASA mission and published background images have source records and speaker-note citations. The conceptual workflow is labelled AI-generated. Scientific charts use actual exported data. Methods, code, narration and drafting used AI assistance; disclose it according to the event’s rules.
