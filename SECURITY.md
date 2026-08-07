# Security Policy

## Supported code

Security maintenance targets the current `main` branch. Historical branches and receipts are retained for provenance but should not be treated as supported runtime releases unless explicitly promoted again.

## Reporting a vulnerability

Do not place credentials, tokens, private case material, connector payloads, or exploit details that could expose connected systems in a public issue or pull request.

Use GitHub private vulnerability reporting when it is available for this repository. Otherwise, contact the maintainers through an established private channel and include only the minimum information needed to reproduce the issue safely:

- affected commit, component, or connector;
- impact and preconditions;
- sanitized reproduction steps;
- whether credentials, external writes, or private data could be affected;
- any known containment or rollback action.

Public disclosure should wait until the affected boundary is contained and maintainers have had a reasonable opportunity to verify the fix.

## Security boundaries

- Secrets belong in environment variables or managed secret stores, never committed source or receipts.
- External or mutating connector capabilities must be explicitly allowlisted and policy-gated.
- Remote transport, authentication, protocol, and authorization failures must fail closed rather than being counted as successful work.
- Generated receipts must not include secret values or private payloads; record identifiers, hashes, timestamps, classifications, and verification results instead.
- A successful local test or workflow does not by itself prove a connected external system is healthy; external state requires read-back verification from that system.

## Credential exposure

If a credential is suspected to have been exposed, treat rotation or revocation as the primary containment action. Removing the value from a later commit does not invalidate copies that may already exist in repository history, logs, caches, or artifacts.
