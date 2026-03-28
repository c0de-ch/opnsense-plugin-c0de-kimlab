#!/usr/bin/env python3
"""Build a FreeBSD pkg repository index from .pkg files.

Usage: python3 build-repo.py <pkg-dir> <output-dir>
Example: python3 build-repo.py /tmp/pkgs /tmp/repo

Creates packagesite.txz, meta.txz, and meta.conf in output-dir.
Expects .pkg files in pkg-dir/All/.
"""

import hashlib
import io
import json
import lzma
import os
import subprocess
import sys
import tarfile


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest_from_pkg(pkg_path):
    """Read +COMPACT_MANIFEST from a .pkg file (tar.zst archive)."""
    # Decompress zstd to tar, then read manifest
    result = subprocess.run(
        ["tar", "-xf", pkg_path, "--zstd", "-O", "+COMPACT_MANIFEST"],
        capture_output=True,
    )
    if result.returncode != 0:
        # Try without --zstd (might be tar.xz)
        result = subprocess.run(
            ["tar", "-xf", pkg_path, "-O", "+COMPACT_MANIFEST"],
            capture_output=True,
        )
    if result.returncode != 0:
        raise RuntimeError(f"Cannot read manifest from {pkg_path}: {result.stderr.decode()}")
    return json.loads(result.stdout)


def make_txz(filename, content_name, content_bytes):
    """Create a .txz (tar.xz) archive containing a single file."""
    xz_data = io.BytesIO()
    with lzma.open(xz_data, "w", format=lzma.FORMAT_XZ) as xz:
        # Create tar inside xz
        tar_data = io.BytesIO()
        with tarfile.open(fileobj=tar_data, mode="w") as tar:
            info = tarfile.TarInfo(name=content_name)
            info.size = len(content_bytes)
            tar.addfile(info, fileobj=io.BytesIO(content_bytes))
        xz.write(tar_data.getvalue())

    with open(filename, "wb") as f:
        f.write(xz_data.getvalue())


def build_repo(pkg_dir, output_dir):
    all_dir = os.path.join(pkg_dir, "All")
    if not os.path.isdir(all_dir):
        print(f"No All/ directory in {pkg_dir}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "All"), exist_ok=True)

    # Process each .pkg file
    packagesite_lines = []
    for pkg_file in sorted(os.listdir(all_dir)):
        if not pkg_file.endswith(".pkg"):
            continue

        pkg_path = os.path.join(all_dir, pkg_file)
        print(f"Processing {pkg_file}...")

        # Read manifest
        manifest = read_manifest_from_pkg(pkg_path)

        # Add repo-specific fields
        manifest["sum"] = sha256_file(pkg_path)
        manifest["pkgsize"] = os.path.getsize(pkg_path)
        manifest["path"] = f"All/{pkg_file}"
        manifest["repopath"] = f"All/{pkg_file}"

        packagesite_lines.append(json.dumps(manifest, separators=(",", ":")))

        # Copy pkg to output
        output_pkg = os.path.join(output_dir, "All", pkg_file)
        if os.path.abspath(pkg_path) != os.path.abspath(output_pkg):
            import shutil
            shutil.copy2(pkg_path, output_pkg)

    if not packagesite_lines:
        print("No .pkg files found")
        sys.exit(1)

    # Write packagesite.yaml (one JSON per line)
    packagesite_yaml = "\n".join(packagesite_lines) + "\n"

    # Create packagesite.txz
    make_txz(
        os.path.join(output_dir, "packagesite.txz"),
        "packagesite.yaml",
        packagesite_yaml.encode(),
    )

    # Write meta.conf
    meta_conf = 'version = 2;\npacking_format = "txz";\nmanifests = "packagesite.yaml";\nmanifests_archive = "packagesite";\n'

    with open(os.path.join(output_dir, "meta.conf"), "w") as f:
        f.write(meta_conf)

    # Create meta.txz
    make_txz(
        os.path.join(output_dir, "meta.txz"),
        "meta",
        meta_conf.encode(),
    )

    print(f"\nRepository built: {len(packagesite_lines)} package(s)")
    for line in packagesite_lines:
        m = json.loads(line)
        print(f"  {m['name']}-{m['version']} ({m['pkgsize']} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <pkg-dir> <output-dir>")
        sys.exit(1)
    build_repo(sys.argv[1], sys.argv[2])
