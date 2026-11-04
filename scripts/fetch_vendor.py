"""Download the pinned third-party JS libraries into web/vendor/.

Packages come from the npm registry as tarballs; each one is checked against
its pinned sha512 integrity hash before anything is extracted. Only the files
the app needs are copied (no source maps, typings or legacy builds).

Usage:  python scripts/fetch_vendor.py [--force]
"""

import argparse
import base64
import hashlib
import io
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "web" / "vendor"
REGISTRY = "https://registry.npmjs.org"

# name, version, sha512 integrity, destination folder, {tarball prefix: dest subfolder}
PACKAGES = [
    {
        "name": "monaco-editor",
        "version": "0.57.0",
        "integrity": "sha512-5BkI9KGoqrNvBGUe15/QlZq3OooZ8WLg1AxTpaqHRCP3HNpzPPZKE2EDz8M7c+VRmCeUw1Brp4cx/PWm3kI/5A==",
        "dest": "monaco",
        "files": {"min/vs/": "vs/", "LICENSE": "LICENSE"},
    },
    {
        "name": "pdfjs-dist",
        "version": "6.4.299",
        "integrity": "sha512-AVl138zALtfaAPvADulE0PZThbYzCBS79nL4pOSL/6Sm/4AH5A21BD9VHt97OlCuzJuCpmeZtAtkinisF4Vb1g==",
        "dest": "pdfjs",
        "files": {
            "build/pdf.min.mjs": "build/pdf.min.mjs",
            "build/pdf.worker.min.mjs": "build/pdf.worker.min.mjs",
            "web/pdf_viewer.mjs": "web/pdf_viewer.mjs",
            "web/pdf_viewer.css": "web/pdf_viewer.css",
            "web/images/": "web/images/",
            "cmaps/": "cmaps/",
            "standard_fonts/": "standard_fonts/",
            "wasm/": "wasm/",
            "iccs/": "iccs/",
            "LICENSE": "LICENSE",
        },
    },
    {
        "name": "typo-js",
        "version": "1.3.2",
        "integrity": "sha512-Z1YkJ7IIYNrFeOxAlHUercY4Q2I+PhYD/3VkWpJGy/Oqudy3bFpNcQxnv6Oa9fTSXCHPGz1eDoX1bZYm2Z891A==",
        "dest": "typo",
        "files": {"typo.js": "typo.js", "README.md": "README.md"},
    },
    {
        "name": "dictionary-en",
        "version": "4.0.0",
        "integrity": "sha512-3NHnE1uq33ZE/CIwaZ6gqxa4BnglHnxeAcTM0GJ7cmtRGcvX9InMK/IqLtYcUMFCUpUNgybH+DzkqdgAo3F1zg==",
        "dest": "dictionaries/en",
        "files": {"index.aff": "index.aff", "index.dic": "index.dic", "license": "license"},
    },
    {
        "name": "dictionary-en-gb",
        "version": "3.0.0",
        "integrity": "sha512-gU/dwC9xGYPh/0CCcmGNXO8OwSgOySAqevcSXxADCsgUD+tr6OJ52u7XaC7No7dNssvdUSfVjkzcqLrRZq3kPA==",
        "dest": "dictionaries/en-GB",
        "files": {"index.aff": "index.aff", "index.dic": "index.dic", "license": "license"},
    },
    {
        "name": "dictionary-ca",
        "version": "3.0.0",
        "integrity": "sha512-h+crBYqX/X7cEU3cFAEgwIojOZTAw1wW4ybYN5Aum9f1oZ+8ULO/GGglLs8m8UBBGtSVLyoYf0CdvX8WKt8VDg==",
        "dest": "dictionaries/ca",
        "files": {"index.aff": "index.aff", "index.dic": "index.dic", "license": "license"},
    },
    {
        "name": "dictionary-es",
        "version": "4.0.0",
        "integrity": "sha512-8J3IYdaHYmkojxqhB+DneQpek6N/s3MwbVk3bPNGQSTBT5kxJtmbuiT0LSDP0Al6K9Vevo1sjspG8AGP9Yvxiw==",
        "dest": "dictionaries/es",
        "files": {"index.aff": "index.aff", "index.dic": "index.dic", "license": "license"},
    },
]

MANIFEST = VENDOR / "VERSIONS.json"


def download(pkg):
    url = f"{REGISTRY}/{pkg['name']}/-/{pkg['name']}-{pkg['version']}.tgz"
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    algo, expected = pkg["integrity"].split("-", 1)
    actual = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if actual != expected:
        raise RuntimeError(f"integrity mismatch for {pkg['name']}@{pkg['version']}")
    return data


def target_for(member_name, files):
    """Map a tarball member to its destination path, or None to skip it."""
    path = PurePosixPath(member_name)
    if path.parts[0] != "package" or ".." in path.parts:
        return None
    rel = "/".join(path.parts[1:])
    if rel.endswith(".map"):
        return None
    for src, dst in files.items():
        if src.endswith("/") and rel.startswith(src):
            return dst + rel[len(src):]
        if rel == src:
            return dst
    return None


def install(pkg, data):
    dest = VENDOR / pkg["dest"]
    if dest.exists():
        shutil.rmtree(dest)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            rel = target_for(member.name, pkg["files"])
            if rel is None:
                continue
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(tar.extractfile(member).read())
            count += 1
    if count == 0:
        raise RuntimeError(f"no files extracted from {pkg['name']}")
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download everything")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    VENDOR.mkdir(parents=True, exist_ok=True)

    for pkg in PACKAGES:
        label = f"{pkg['name']}@{pkg['version']}"
        if not args.force and manifest.get(pkg["name"]) == pkg["version"] and (VENDOR / pkg["dest"]).exists():
            print(f"  ok        {label}")
            continue
        print(f"  fetching  {label} ...", end="", flush=True)
        count = install(pkg, download(pkg))
        manifest[pkg["name"]] = pkg["version"]
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f" {count} files")

    print(f"Vendor libraries ready in {VENDOR.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # report cleanly instead of a traceback
        print(f"\nerror: {exc}", file=sys.stderr)
        sys.exit(1)
