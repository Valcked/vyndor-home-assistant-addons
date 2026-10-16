# Vyndor Home Assistant — Supported Architectures

## M-002 Architecture Support Contract

Status: ACCEPTED BY DESIGN — pending audit approval.

## Supported Architectures

| Component | Version | HA architectures | OCI platforms |
|---|---|---|---|
| Vyndor Agent | 0.1.5 | amd64, aarch64 | linux/amd64, linux/arm64 |
| Vyndor Home | 0.1.2 | amd64 | linux/amd64 |

## Deployment Policy

Vyndor Home is officially AMD64-only for the current
0.x release series.

Vyndor Agent supports AMD64 and ARM64.

A complete Vyndor Home + Agent installation currently
requires an AMD64 Home Assistant host.

ARM64 support for Vyndor Home is not advertised,
promised or considered tested.

## Future ARM64 Support

ARM64 support for Vyndor Home may only be enabled
after all of the following are completed:

1. Build an ARM64 container image.
2. Validate runtime functionality on ARM64.
3. Run security and integration tests.
4. Verify Home Assistant Supervisor compatibility.
5. Update the add-on catalog architecture list.
6. Update the release contract and platform digests.
7. Pass the complete CI release gates.

## Security Requirements

The advertised architectures must match the
published container manifests.

Unsupported architectures must not be advertised.

Existing release tags must not be overwritten
to introduce new architecture support.

## Audit Decision

Finding: VYNDOR-M-002

Classification: Architecture support limitation.

Decision: AMD64-only Vyndor Home is intentional.

Status: Pending final audit review.

Production release: Not authorized by this document.
