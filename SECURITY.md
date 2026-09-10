# Security

## Reporting

Open a private security advisory on the GitHub repository
(Security -> Advisories -> Report a vulnerability). Please do not file public
issues for vulnerabilities.

## What the application does

- Uploads are validated by extension, content checks (PDF magic bytes,
  UTF-8/UTF-16 decoding), size enforced while reading, page and text limits.
  Stored files use server-generated names inside `DATA_DIR/uploads`; the
  display filename is never used as a path.
- reStructuredText is treated as plain text; no directives are executed.
  PDFs are read with pypdf; no JavaScript, forms, or external resources are
  processed.
- Retrieved document text is passed to the model inside delimited evidence
  blocks with instructions to ignore embedded instructions. This lowers but
  does not remove prompt-injection risk; the answer path cannot trigger
  tools, network calls, or configuration changes.
- When `API_KEY` is configured, all `/api/v1` routes require it (constant-time
  comparison). Without it the server runs in local mode with no
  authentication and bulk deletion is disabled. There is no per-user
  authorization or tenant isolation.
- Error responses hide internal details outside development mode; logs do
  not include document contents or query text by default.
- Metadata is restricted to flat scalar values; reserved keys are rejected.

## What it does not do

- No rate limiting, encryption at rest, RBAC, SSO, or audit log.
- Deletion removes application-controlled data only.
- Dependencies are pinned but not continuously monitored beyond the CI
  Trivy scan (advisory) and verified-secret scan (enforced).
