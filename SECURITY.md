# Security notes

SmartCourse AI is a **local academic/portfolio prototype**, not a production multi-user service. It has no user authentication or per-user authorization. Session identifiers must be treated as bearer references. **Do not expose the Flask service or PostgreSQL to the public internet.**

## Local setup

- Keep `.env` out of Git. Set your own `ANTHROPIC_API_KEY` and database credentials; the `.env.example` file contains placeholders only.
- Use `FLASK_DEBUG=false` and bind the Flask server and PostgreSQL to localhost.
- Avoid uploading real student records, private course materials, or credentials to the repository.
- Rotate any API key that has been disclosed in screenshots, logs, or messages.
- Production deployment would require authentication, authorization, TLS, rate limiting, monitoring, and a security review.

For security concerns, please contact the repository maintainer privately rather than opening a public issue with sensitive details.
