# ARGUS Release Architecture

This repository is a public distribution boundary for a private desktop project. It
contains no ARGUS application source.

## Components

```text
Private argus-command-center tag
        │ read-only SSH deploy key
        ▼
Public GitHub Actions release workflow
        ├── macOS Apple Silicon runner ── DMG
        ├── macOS Intel runner ────────── DMG
        └── Windows x64 runner ────────── NSIS + MSI
                         │
                         ▼
                Draft GitHub Release
                         │ verify source SHA + assets
                         ▼
                Public GitHub Release
```

## Trust boundary

- `ARGUS_SOURCE_DEPLOY_KEY` is a repository secret containing a dedicated SSH key.
- The matching deploy key has **read-only** access to
  `posidron/argus-command-center`.
- `keys/artifact-public.pem` is intentionally public and is the only encryption key
  available to native build jobs. `ARGUS_ARTIFACT_PRIVATE_KEY` is exposed only to
  the trusted publisher job.
- The workflow has no `pull_request`, `push` or fork-controlled trigger; only a
  maintainer can dispatch a source tag.
- Every third-party action is pinned to an immutable commit SHA.
- Checkout does not persist source credentials for later build steps.
- Private Git operations run through a quiet trusted wrapper with pinned GitHub SSH
  host keys; detached commit subjects and Git diagnostics are never emitted publicly.
- Private source commands run only in read-scoped jobs, with GitHub output/environment
  command channels and runtime tokens removed.
- Build output is captured rather than streamed into public logs.
- Intermediate installers and failure logs use per-file AES-256-GCM keys wrapped by
  a 4096-bit RSA public key before entering public workflow-artifact storage. Build
  jobs have no decryption secret.
- npm, uv and Cargo caches are deliberately not persisted from public build jobs.
- Only the trusted publisher job has release-write permission; it never executes
  private source code.
- The public repository receives verified installers and release metadata, never
  private source history or plaintext intermediate artifacts.

## Release integrity

1. Metadata checks out the requested private tag and runs the source repository's
   manifest-version validator.
2. The resolved source commit SHA is passed to every native matrix job; jobs never
   rebuild a moving branch or tag.
3. Each read-scoped runner creates the architecture-matched PyInstaller sidecar and runs its
   authenticated startup, timezone-data and lifetime-shutdown smoke test before
   Tauri packaging.
4. Matrix jobs re-checkout trusted packager code after private commands finish,
   clear packaging directories, encrypt predictable architecture-labelled outputs
   with the repository public key and upload only explicit ciphertext files with
   one-day retention.
5. The publisher checks out only the private tag metadata, verifies it still resolves
   to the original SHA, decrypts and validates all hashes and sizes, and checks the
   draft identity.
6. Existing draft assets are removed, then exactly both DMGs, the NSIS setup
   executable and MSI are uploaded.
7. Only then is the release made public. Failed builds leave a resumable draft;
   published releases are never modified by a rerun.

## Signing boundary

Current artifacts are unsigned. Future Apple Developer ID/notarization and Windows
Authenticode credentials must be dedicated release secrets and must never be stored
in either repository.
