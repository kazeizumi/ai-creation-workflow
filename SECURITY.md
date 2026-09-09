# Security

Never commit API tokens, instance passwords, signed URLs, private reference
media, generated client footage, or manifests containing local absolute paths.

Load secrets from environment variables or a local ignored `.env` file. The
included AutoDL client reads `AUTODL_TOKEN`; it does not require a token in a
manifest or command-line argument.

Before publishing a fork, run:

```bash
python scripts/verify_release.py
```

If a secret has been committed, revoke it before rewriting Git history. Removing
it from the latest file does not invalidate copies in earlier commits.
