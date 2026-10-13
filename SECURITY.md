# Security

Do not put passwords, session cookies, API keys, payment URLs or private account responses in GitHub issues. Report bugs with redacted request shapes and HTTP status codes. Rotate a key in the GenRouter cabinet if it has been disclosed.

The companion uses fixed HTTPS GenRouter hosts and does not follow redirects with credentials. It never reads your browser or email credential databases. Passwords/email codes are entered locally and not retained. Read-only agent tools omit full key secrets; full export requires an explicit interactive CLI command.

Windows private account state is protected with current-user DPAPI. Other platforms use permission-restricted files, not encrypted storage. The Hermes `.env` remains plaintext. Back up private credentials separately from source, and protect the OS account and backups.

Experimental checkout needs an opt-in environment flag and explicit amount confirmation. No card data is collected, and checkout creation is not payment completion. Mutations are not automatically retried.

The owner-authorized GitHub issue reporter credential is intentionally distributed
with the plugin. Its reversible encoding does not protect it. This exception is
only for repository Issues access, never GenRouter credentials or GitHub code/admin
access. Assume anyone can recover it; revoke it if abused and release an update.

Diagnostic collection is local. Publication requires report preview and explicit
consent. Logged-in GitHub CLI users can choose their own identity. Known secrets,
tokens, cookies and email addresses are redacted; no prompt history or raw HTTP
payloads are collected. Optional user-selected logs must be reviewed manually.
Failed submission prepares a mail draft rather than sending without permission.
Deduplication scans open and closed issues; simultaneous cross-device submissions
are not atomic. No mutating request is automatically retried.
