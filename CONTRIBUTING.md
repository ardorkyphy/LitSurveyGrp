# Contributing

LitSurveyGrp is an alpha-stage research tool. Contributions should preserve the
current principle: metadata-first survey workflows, optional PDF acquisition,
and research-facing outputs.

## Development Setup

```powershell
python -m pip install -e .
python -m pip install -r requirements-dev.txt
```

Run tests before proposing changes:

```powershell
python -m pytest tests -q
```

The test suite is designed to avoid real network access. Add mock-based tests
for downloader, metadata, PDF, classification, reference, and CLI behavior.
Real network experiments should be treated as manual validation and should not
be required for CI.

## Generated Files

Do not commit local experiment outputs, PDFs, model caches, or API keys. These
are ignored by default:

- `.env`
- `papers/`
- `results/`
- `*.pdf`
- `*.egg-info/`
- `.pytest_cache/`

## API and Publisher Use

Use open scholarly APIs and open-access full-text sources responsibly. Keep
request intervals conservative for large runs, and do not add behavior intended
to bypass paywalls or publisher access controls.

## Design Rules

- Keep metadata collection separate from PDF downloading where practical.
- Prefer OpenAlex/Crossref/Europe PMC/Unpaywall-style open infrastructure over
  unstable scraping.
- Keep research statistics focused on scholarly insight, not operational
  failure counts.
- Preserve Chinese path support.
- Keep CLI behavior documented and covered by tests.

