# Acquisition update — 14 November 2026

Twelve actual NASA regional exports have now been acquired and processed separately. The review below records what Aadarsh’s supplied handbook contained at the initial review; it does not describe the current data availability. Use docs/research_findings.md and results/ for current measured findings. Aadarsh’s executable statistical functions are still required.

# Review of Aadarsh's TrendTrace handbook

Reviewed 13 November 2026. Source: TrendTrace-2.pdf, 42 pages, prepared by Aadarsh Praveen Kumar for Team Copernicus.

## What the supplied PDF provides

The handbook supplies research context, product-selection proposals, region boxes, method definitions, proposed function input/output contracts, validation plans and presentation responsibilities. It confirms that Sritharan owns acquisition, processing, anomalies, rainfall indicators and data validation Part A. Aadarsh owns trend analysis, confidence/evidence, interaction and statistical validation Part B.

No raw regional time series, completed trend-result tables, executable functions, repository URL or embedded data files were found in this PDF. Its numerical examples must not be treated as observations or calculated findings. In particular, page 26 explicitly labels its 258/264 coverage, slope interval and p/q values as display examples.

## Useful information now available

- Pages 13–14: proposed IGP and TN boxes, 2003–2024 period, season labels, 264 monthly timestamps and 8,036 daily dates per region-variable combination. Expected counts do not mean complete retrievals exist.
- Pages 16–18: first monthly and later daily handoff requirements, metadata and file outputs.
- Pages 20–22: rainfall indicators and anomaly definitions, including quality conditions.
- Pages 24–25: conceptual function inputs for compute_trend, compute_evidence, rain_event_composite and monthly_association. These are descriptions, not callable Python signatures or code.
- Pages 29–30: independent validation responsibilities.
- Pages 37–38: decisions still requiring agreement.

## Differences to resolve before implementation

1. IMERG version. The original assignment prefers V07 consistently. The newer handbook allows V08 Final after a complete retrospective-coverage and documentation check. The user's Giovanni screenshot establishes a V07 monthly listing, not V08 availability. Retain V07 as the current proposed source until an agreed change. Do not mix versions or runs.
2. CSV fields. The original shared contract has nine fields. The handbook adds data_version and method as row fields. Agree with Group 1 whether to add them to the CSV or retain them in file-level metadata. If an existing contract is frozen, version the change.
3. Source identifiers. The original plan and handbook examples use different IMERG identifier ordering. Choose one exact mapping with Group 1 and Aadarsh. Display labels do not determine API identifiers automatically.
4. Coverage meaning. The handbook's generic fraction definition needs the original contract's distinction: monthly temporal availability versus daily spatial valid-cell fraction when known. Unknown fractions stay missing. Record the denominator and aggregation.
5. Missing-time statistics. Page 24 strengthens the original code sketch: dropping missing months before an autocorrelation calculation can compress time. Aadarsh must select and document a gap-aware approach or an explicitly justified complete-period sensitivity. Using real x coordinates for Sen slopes solves slope spacing, but does not alone solve autocorrelation gaps.
6. Confidence intervals. A Hamed–Rao p-value does not automatically correct a conventional Theil–Sen interval for time dependence. Document the interval procedure and limitations.
7. Evidence labels. The handbook leaves raw p versus adjusted q open. Freeze the multiple-testing family, label input, and required sensitivity set before looking at results. A missing optional sensitivity cannot silently count as agreement.
8. Threshold details. Agree percentile interpolation/ties, minimum same-month sample count, treatment of non-positive AOD, seasonal completeness, and dry-spell interruptions by missing days. These details affect reproducibility.

## First handoff specification for Sritharan

Four core monthly series: rainfall and Aqua AOD for IGP and TN. Supply source manifests, provenance, units, timestamps, explicit gaps and available quality/coverage metadata. Keep coverage unknown until measured. Aadarsh reviews the files before trend analysis.

Daily handoff: aligned IMERG rainfall and Aqua AOD with explicit dates, missingness, UTC-day convention and available spatial coverage. This supports Aadarsh's event comparison and Sritharan's rainfall indicators.

No handbook examples should be pasted into these scientific files. No validation checklist should be marked passed before actual execution.

## Files still needed if Aadarsh has produced them separately

- Original or processed NASA CSV/NetCDF/HDF files and their metadata.
- His actual Python functions or repository link, including dependencies and exact calling signatures.
- Any calculated trend/evidence/interaction JSON, CSV or validation logs, tied to input data and code versions.
- The team's agreed current contract and decisions log.

These are complementary inputs. Downloading and preparing primary data remains Sritharan's responsibility under the handbook; the PDF does not establish that Aadarsh has already downloaded those data.

## Speaker notes and disclosure

The accompanying PowerPoint includes source links and detailed methods in speaker notes. It distinguishes published background, team proposals, screenshots and unresolved empirical work. AI helped review the handbook and prepare the briefing; include this assistance in the team's AI-use disclosure. The expanded briefing is not a final competition submission deck.
