# Vyndor Release Compatibility Matrix

## VYNDOR-M-003

Status: Under review

## Release identities

| Component | Release | Source commit |
|---|---|---|
| Agent | 0.1.5 | 55947fc |
| Home | 0.1.2 | 6451d74 |
| Display | 0.1.0 | 591e4fe |
| Control | Not established | No release tag identified |

Control's development commit is not evidence of
the version currently deployed in production.

## Compatibility evidence

| Components | Contract | Status |
|---|---|---|
| Home 0.1.2 / Display 0.1.0 | Display Access v1 | PROTOCOL_MATCH |
| Home 0.1.2 / Display 0.1.0 | Pairing v3 | PROTOCOL_MATCH |
| Home 0.1.2 / Agent 0.1.5 | Owner approval / commissioning | UNKNOWN |
| Control / Agent 0.1.5 | Agent API | UNKNOWN |
| Control / Home 0.1.2 | Installation management | UNKNOWN |

## Verified protocol evidence

Home 0.1.2 and Display 0.1.0 contain
byte-identical Display Access protocol definitions.

Home 0.1.2 and Display 0.1.0 also contain
byte-identical Pairing protocol definitions.

This proves protocol source equality, not complete
end-to-end runtime compatibility.

## Existing test coverage

Home 0.1.2 contains tests for:
- Display security boundaries
- Trusted Display binding
- Home Agent owner approval

Agent 0.1.5 contains tests for:
- Home installation security
- Home Local API
- Home owner approval

These tests exist in the release source trees.
Cross-release execution is not yet established.

## Identity Probe

Display Identity Probe v1 was added after
the currently published Home and Display releases.

Its compatibility must be validated before
publishing the corresponding new releases.

## Update policy

Compatibility information is advisory.

A user with sufficient permissions may continue
an update despite compatibility warnings.

Unknown compatibility must be reported as unknown,
not automatically classified as incompatible.

Security protocol validation, authentication and
authorization remain mandatory.

## Release policy

Update this matrix when supported component
combinations are tested or new releases are issued.

Only mark a combination VERIFIED when appropriate
integration evidence is available.

No additional update-blocking mechanism is required
by this compatibility documentation.

## Cross-repository OWNER approval evidence

Test date: 2026-10-16

Home source commit: `38cab59ed0db881aa020eabd5182bde3b66cfb43`

Agent source commit: `e176e5d7f2f1a500d3778fbdb6842cd9689db16b`

Result: PASS (5 checks)

The current featurebranch implementations were
tested against each other using their real
TypeScript and Python protocol payload builders.

Successful checks:
- Identical OWNER approval START payloads.
- Identical OWNER approval CHALLENGE payloads.
- Invalid nonce rejected by both implementations.
- Node.js Ed25519 signature verified in Python.
- Modified claim rejected by signature verification.

Limitations:
- The test used temporary cryptographic keys.
- The Agent coordinator was not exercised end-to-end.
- No HTTP communication or Control persistence was tested.
- N-1/N/N+1 release combinations remain unverified.
- This was a temporary manual test, not yet a CI gate.

Therefore, this evidence does not establish full
runtime or published-release compatibility.
