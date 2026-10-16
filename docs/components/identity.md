# Identity (embedded Dex IdP)

The server ships an **embedded Dex** identity provider, so local users work out of
the box and are managed from the Dashboard — no external IdP is required.

- Issuer: `https://<domain>/oauth2`.
- `auth.sessionCookieEncryptionKey` is the session cookie key
  (`vault_session_cookie_encryption_key`, an auto-generated internal — leave it
  unedited; it must match across instances only for HA / an external relay, both
  out of scope here).
- Redirect URIs: dashboard `/nb-auth` and `/nb-silent-auth`; CLI
  `http://localhost:53000/`.

External OIDC providers can run alongside local users, but are **runtime tenant
config, not managed here**. See [../IDP.md](../IDP.md).
