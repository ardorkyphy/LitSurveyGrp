# Security Policy

## Secrets

Do not commit API keys, tokens, cookies, session headers, institutional access
credentials, or private PDFs. Keep local credentials in `.env` or in your shell
environment. `.env` is ignored by default; `.env.example` is the only
environment file intended for version control.

Before publishing a branch or release, check:

```powershell
git status --short
git status --ignored --short .env papers results
```

## Responsible Access

LitSurveyGrp is designed to use open scholarly APIs and accessible full-text
sources. Do not add features that bypass paywalls, authentication, publisher
access controls, or robots/terms restrictions.

Use conservative request intervals for large metadata runs and avoid hammering
publisher sites or public APIs.

## Reporting Issues

If you find a security issue, credential leak, or behavior that may violate
publisher access controls, report it privately to the maintainer instead of
opening a public issue with sensitive details.

