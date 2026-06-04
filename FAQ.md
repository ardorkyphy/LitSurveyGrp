# FAQ

## Is LitSurveyGrp a paper downloader?

Not exactly. It is a literature-survey automation tool. It discovers papers,
enriches metadata, clusters topics, analyzes cited references, writes research
statistics, and can optionally download accessible PDFs.

## Why are fewer PDFs downloaded than papers collected?

PDF availability is uneven. Some papers have metadata but no open PDF. Some
publishers return HTTP 403, require institutional access, or expose only HTML.
LitSurveyGrp does not bypass paywalls. For larger surveys, run metadata first
and then download only top-ranked PDFs:

```powershell
lsg run-survey --journal nature-aging --per-journal-limit 150 --metadata-only --papers-dir papers --results-dir results
lsg download-pdfs --manifest results\classified_manifest.json --papers-dir papers --results-dir results --top 20
```

## Why do citation counts differ from Google Scholar?

Citation counts come from open sources such as OpenAlex, Crossref, Europe PMC,
or optional Semantic Scholar. Their coverage and counting rules differ from
Google Scholar, Web of Science, and Scopus. Treat the numbers as practical
ranking signals, not formal bibliometric truth.

## Why are topic labels sometimes odd?

Topic labels are generated automatically from titles, abstracts, and clustered
text. If metadata is sparse or abstracts are missing, clustering and labels can
be weaker. Better metadata usually improves labels.

## Does the project need API keys?

Most workflows can run without paid keys. Optional keys can improve coverage:

- `OPENALEX_API_KEY`: optional OpenAlex configuration.
- `CORE_API_KEY`: optional CORE fallback for open-access files.
- `UNPAYWALL_EMAIL`: recommended contact email for Unpaywall requests.

Keep keys in `.env` or environment variables. Do not commit them.

## Are real network tests part of the test suite?

No. Unit tests should mock network calls. Real network experiments are manual
validation because publisher behavior, regional access, API limits, and service
availability change over time.

## What should I commit?

Commit source code, tests, and docs. Do not commit `papers/`, `results/`, local
PDFs, API keys, model caches, or temporary manifests.

