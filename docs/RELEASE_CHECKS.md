# Release work and evidence boundaries

The project is still a pilot, not a certified public release. Windows source-runtime search works on the builder's Windows 11 host. The standalone GUI/CLI package builds successfully, but local execution is blocked by Application Control (`WinError 4551`). No trust store, signing policy, execution policy or Application Control setting was changed. A permitted environment or approved signing path is needed to test/run that artifact.

## Concrete artifacts

- `packaging/omnifind.spec`: one-folder GUI and console-worker executables. Frozen extraction uses the console worker's original Job Object handshake, limits and selected-root checks. Packaged model paths resolve beside the executable rather than against the working directory.
- `scripts/verify_package.py`: run the actual executables from an unrelated working directory, index new synthetic PDF/TXT/PNG files, perform real local semantic/code search, restart across commands and remove scope while preserving originals. `--allow-unavailable-ocr` is for a runner lacking OCR; it records the gap rather than claiming screenshot success.
- `scripts/assemble_release.py`: model assets, project source, dependency license files/inventory, manifest hashes and an unsigned pilot ZIP. This is an environment inventory, not a complete native-binary SBOM or legal certification.
- `packaging/install.ps1`: verify manifest hashes and install a new per-user version directory, preserving existing versions and the index. `packaging/uninstall.ps1`: remove only the explicitly named owned version under `%LOCALAPPDATA%\OmniFindLocalApp`; preserve `%LOCALAPPDATA%\OmniFindLocal` and all original folders. Both obey the existing PowerShell policy; no bypass instruction is supplied. Script parsing is not an installation test.
- `.github/workflows/windows-release-check.yml`: a separate Windows Server 2025 runner recreates dependencies, downloads only pinned public model assets, tests lifecycle behavior, builds and verifies the executable. This is additional Windows evidence; it is not independent Windows 11 user validation.

## Native Windows checks

The actual Windows common folder dialog was observed and programmatically accepted for a synthetic directory. Native Open and Explorer dispatch were exercised through source authorization; uniquely named original/folder windows appeared and source bytes were preserved. Those observations do not establish manual usability or independently confirm displayed contents/Explorer selection. Test-created viewer/Explorer windows were left open to avoid closing a reused window containing user work.

Qt's Windows accessibility interfaces expose named controls, roles, disabled empty-state actions, populated source text and enabled valid-result actions. Keyboard/large-text checks remain in the desktop automation. Narrator/JAWS use by a human has not been conducted.

## Network audit

WPR reported `0xc5585011`, “Failed to enable the policy to profile system performance.” It did not start recording. The separate socket-table observer samples only the synthetic application and descendants and publishes counts without endpoints. It found loopback socket entries in OCR workers; endpoint classification is required because socket entries alone do not imply internet traffic. A short-lived connection can be missed, attempts may never enter a sampled table, and native OCR system services are not fully attributed. These limits prevent calling it a complete OS egress audit.

An authorized elevated Windows trace with process/service attribution and an offline fresh-file test remains necessary. Do not disable security controls to make a test pass, and do not upload raw traces that may contain unrelated private endpoints.

`scripts/capture_network_trace.ps1` prepares that check for an authorized elevated session. It uses a unique WPR instance, records a synthetic package verification and stops only its own trace in `finally`. It refuses a non-elevated session and makes no policy changes. The private ETL still needs process/service attribution, network-attempt review and lost-event checks; producing a file alone does not pass the audit.

## External gates

[Independent pilot validation](PILOT_VALIDATION.md) provides tasks, counterbalanced baselines, consent boundaries and a result template. No independent participant has been tested by the builder. Another Windows 11 machine, an independent tester/screen-reader user and an approved execution/signing path remain needed. Microsoft-documented Windows OCR package-identity support also needs a supported packaged deployment test.

Mobile architecture is awaiting the user's choice between phone-local indexing and a paired desktop LAN companion. Neither can be truthfully marked implemented or device-tested by the desktop release work.
