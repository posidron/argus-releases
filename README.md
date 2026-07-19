# ARGUS Releases

Public binary distribution for the private
[`posidron/argus-command-center`](https://github.com/posidron/argus-command-center)
project.

This repository contains release automation and downloadable installers only. The
ARGUS source code remains private.

## Downloads

Download the latest release from:

https://github.com/posidron/argus-releases/releases/latest

| Platform | Asset |
| --- | --- |
| macOS Apple Silicon | `ARGUS_<version>_macOS_arm64.dmg` |
| macOS Intel | `ARGUS_<version>_macOS_x64.dmg` |
| Windows x64 | `ARGUS_<version>_Windows_x64-setup.exe` or `.msi` |

The initial builds are unsigned. macOS Gatekeeper or Windows SmartScreen may require
explicit approval before first launch.

## Release process

Maintainers dispatch the `Publish ARGUS desktop release` workflow with a private
source tag such as `v0.3.0`. The workflow:

1. checks out the private source through a dedicated read-only deploy key;
2. resolves the tag to one immutable source commit;
3. creates or resumes one draft and normalizes GitHub's temporary draft tag to the
   requested source tag;
4. builds and smoke-tests native Python sidecars on Windows x64, macOS Apple
   Silicon and macOS Intel;
5. captures private build output instead of printing it to public logs;
6. encrypts all intermediate installers before transferring them as temporary
   workflow artifacts;
7. decrypts and uploads an exact four-file allowlist from a separate trusted
   publisher job;
8. publishes only after all assets and the source-tag SHA are verified.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the trust and release boundaries.

## License

Binary releases are provided for the private ARGUS project. No source-code license
is granted by this distribution repository.
