# Security notes

SmartCourse AI is a **local academic/portfolio prototype**, not a production multi-user service. It has no user authentication or per-user authorization. Session identifiers must be treated as bearer references. **Do not expose the Flask service or PostgreSQL to the public internet.**

## Local setup

- Keep `.env` out of Git. Set your own `ANTHROPIC_API_KEY` and database credentials; the `.env.example` file contains placeholders only.
- Use `FLASK_DEBUG=false` and bind the Flask server and PostgreSQL to localhost.
- Avoid uploading real student records, private course materials, or credentials to the repository.
- Rotate any API key that has been disclosed in screenshots, logs, or messages.
- Production deployment would require authentication, authorization, TLS, rate limiting, monitoring, and a security review.

For security concerns, please contact the repository maintainer privately rather than opening a public issue with sensitive details.


## Previously exposed key: verification still required

The historical [verification record](docs/verification.md) notes an older Anthropic API key whose **revocation could not be confirmed** on 2026-10-09. README or repository edits **cannot revoke an API key**. In the Anthropic console, identify any former or exposed key, revoke it, issue a new key where necessary, and check usage for unexpected calls. Never paste key values into issues or commits. If a key existed in Git history, keep it revoked even after redaction.
