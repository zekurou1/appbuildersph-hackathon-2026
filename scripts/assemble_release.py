"""Assemble an unsigned pilot distribution with hashes, source and dependency notices."""
import hashlib
import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from importlib.metadata import distributions
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-blocked-by-policy", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    package = project / "dist/OmniFindLocal"
    assert (package / "OmniFind.exe").is_file() and (package / "OmniFindCLI.exe").is_file()
    shutil.copytree(project / "models/minilm", package / "models/minilm", dirs_exist_ok=True)
    notices = package / "THIRD_PARTY_NOTICES"
    notices.mkdir(exist_ok=True)
    for name in ["install.ps1", "uninstall.ps1"]:
        shutil.copyfile(project / "packaging" / name, package / name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, notices / "PYTHON-LICENSE.txt")
    if (project / "packaging/notices/APACHE-2.0.txt").is_file():
        shutil.copyfile(project / "packaging/notices/APACHE-2.0.txt", notices / "MINILM-APACHE-2.0.txt")
    inventory = []
    for distribution in distributions():
        name = distribution.metadata["Name"]
        folder = notices / name
        paths = []
        for source in distribution.files or []:
            parts = Path(str(source)).parts
            if any(part.lower() in {"licenses", "license", "legal"} for part in parts) or Path(str(source)).name.lower().startswith(("license", "copying", "notice")):
                original = Path(distribution.locate_file(source))
                if not original.is_file():
                    continue
                relative = Path(*parts[1:]) if parts and parts[0].endswith(".dist-info") else Path(original.name)
                if ".." in relative.parts or relative.is_absolute():
                    continue
                target = folder / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
                paths.append(target.relative_to(package).as_posix())
        inventory.append({"name": name, "version": distribution.version,
                          "declared_license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License"),
                          "license_files": paths})
    (notices / "environment-inventory.json").write_text(json.dumps(inventory, indent=2))
    (notices / "README.txt").write_text(
        "This inventory includes the build environment; it is not an exact native-binary SBOM.\n"
        "Qt/PySide shared libraries are dynamically distributed. See their included license texts and https://doc.qt.io/qtforpython-6/licenses.html.\n"
        "MiniLM model: sentence-transformers/all-MiniLM-L6-v2, Apache-2.0 per pinned model card. See models/minilm/asset-manifest.json.\n"
        "No new license is granted for project code by this inventory.\n")
    tracked = subprocess.check_output(["git", "-c", f"safe.directory={project.as_posix()}", "ls-files", "-z"], cwd=project)
    with zipfile.ZipFile(package / "PROJECT_SOURCE.zip", "w", zipfile.ZIP_DEFLATED) as source:
        for raw in tracked.split(b"\0"):
            if raw:
                relative = Path(raw.decode("utf-8"))
                if (project / relative).is_file():
                    source.write(project / relative, relative.as_posix())
    for name in ["PILOT_VALIDATION.md", "RELEASE_CHECKS.md"]:
        if (project / "docs" / name).is_file():
            shutil.copyfile(project / "docs" / name, package / name)
    entries = {}
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.name != "release-manifest.json":
            with path.open("rb") as stream:
                entries[path.relative_to(package).as_posix()] = {"bytes": path.stat().st_size,
                    "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    manifest = {"format": "unsigned-one-folder-pilot", "files": entries,
                "local_execution": "Blocked by this host's Application Control policy (WinError 4551); policy unchanged" if args.local_blocked_by_policy else "Unverified by this assembler",
                "release_ready": False,
                "limits": ["Requires permitted execution environment; no trust or policy bypass instructions",
                           "Independent Windows 11 user validation and package identity remain unverified"]}
    (package / "release-manifest.json").write_text(json.dumps(manifest, indent=2))
    archive = shutil.make_archive(str(project / "dist/OmniFindLocal-pilot"), "zip", package.parent, package.name)
    with Path(archive).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    report = {"archive": Path(archive).name, "sha256": digest, "bytes": Path(archive).stat().st_size,
              "file_count": len(entries), "release_ready": False}
    (project / "reports/runtime/release-artifact.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
