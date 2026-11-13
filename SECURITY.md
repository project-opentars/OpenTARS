# Security

## Reporting a problem

Write to **projectopentars@gmail.com** before opening a public issue. Please include:

- the openTARS version (`opentars --version`),
- your system (Linux distribution, Windows or macOS version),
- what you did and what happened.

Reports are answered as soon as possible. Fixes ship as a new release, and installed copies offer the update on their own.

## Supported versions

Only the latest release gets fixes. Today that is **5.3 Tesseract**.

## How openTARS protects you

- Commands that delete data, change the system, send or install wait for your Allow. These checks are fixed rules in the code, not AI.
- The models and the engine are checked against a fixed SHA-256 before they are used.
- Release files carry a GitHub attestation. See [Verify your download](https://project-opentars.github.io/OpenTARS/verify.html).
- Missions in a virtual machine see none of your files, and nothing they make reaches your computer without your choice.

More in the [privacy and security page](https://project-opentars.github.io/OpenTARS/privacy.html).
