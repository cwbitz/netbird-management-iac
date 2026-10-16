# Identity providers (IdP)

NetBird ships an embedded **Dex** IdP, so local users work out of the box and are
managed from the Dashboard. External **OIDC** providers — Google, Microsoft Entra,
Okta, Keycloak, Zitadel, **Authentik**, Pocket ID, or any generic OIDC provider —
can run alongside them.

Adding an IdP is runtime tenant config and is **not** managed by this project (the
`community.ansible_netbird` `configure` role does not handle identity providers).
Use the Dashboard (**Settings → Identity Providers**) or
`POST /api/identity-providers`.

## Generic OIDC

1. Register a **confidential** OAuth2/OpenID app at the provider and put the
   NetBird redirect URL in it.
2. Add a *Generic OIDC* IdP in NetBird with the provider's issuer, e.g.
   `https://authentik.example.com/application/o/netbird/`.

## Remote-access gotchas

- Both the user's browser **and** the NetBird server must reach the issuer
  (discovery, JWKS, token, and the login/consent pages) over valid public TLS.
- If the issuer sits behind an IP allowlist limited to LAN/CGNAT sources, public
  browsers and the server are rejected; expose the OIDC/login paths or allowlist
  the required source IPs.
- **JWT group sync** follows the provider's claim: Authentik's `profile` scope
  includes `groups` (enable JWT group sync in NetBird and use the `groups` claim);
  Zitadel exposes *roles* and needs an Action to flatten them.

See the NetBird documentation for the full per-provider reference.
