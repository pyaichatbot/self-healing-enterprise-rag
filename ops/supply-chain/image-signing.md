# Image Signing Policy

## Requirements
- Sign container images in CI before registry push.
- Verify signatures at deploy admission.
- Track signing identities and rotation cadence.

## Placeholder Tooling
- Sigstore Cosign for signing/verification
- Policy engine enforcement in cluster admission
