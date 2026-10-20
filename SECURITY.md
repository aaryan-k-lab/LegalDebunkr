# Security

- Secrets live only in `.env` (git-ignored) or your host's secret store. Never commit them.
- If a key is ever committed or pasted publicly, rotate it in the Azure portal immediately. Deleting the commit does not make it safe.
- Report vulnerabilities by opening a private security advisory on this repository.
