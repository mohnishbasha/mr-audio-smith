# Security policy

## Supported versions

The latest minor release receives security fixes.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub Security Advisories
(Security tab, "Report a vulnerability") on `mohnishbasha/mr-audio-smith`. Do not open a public
issue. You will get an acknowledgement within 72 hours and a fix or mitigation plan within 14 days.

## Scope highlights

- SSRF and path traversal in the fetcher and output writers
- Any way to synthesize a cloned voice without a consent record
- Authentication bypass on `mr-audio-smith serve` or Studio
- Secrets leaking into manifests, logs, or error messages

## Design commitments

Local-first, zero telemetry, consent enforced in core, subprocesses only with argument arrays,
servers bind to 127.0.0.1 by default. See `docs/ARCHITECTURE.md` section 9.
