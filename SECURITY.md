# Security

Do not put passwords, session cookies, API keys, payment URLs or private account responses in GitHub issues. Report bugs with redacted request shapes and HTTP status codes. Rotate a key in the GenRouter cabinet if it has been disclosed.

The companion uses fixed HTTPS GenRouter hosts and does not follow redirects with credentials. It never reads your browser or email credential databases. Passwords/email codes are entered locally and not retained. Read-only agent tools omit full key secrets; full export requires an explicit interactive CLI command.

Windows private account state is protected with current-user DPAPI. Other platforms use permission-restricted files, not encrypted storage. The Hermes `.env` remains plaintext. Back up private credentials separately from source, and protect the OS account and backups.

Experimental checkout needs an opt-in environment flag and explicit amount confirmation. No card data is collected, and checkout creation is not payment completion. Mutations are not automatically retried.
