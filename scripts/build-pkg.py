#!/usr/bin/env python3
"""Build a FreeBSD .pkg from the plugin source tree.

Usage: python3 build-pkg.py <version> <src-dir> <output-file>
Example: python3 build-pkg.py 1.0.2 net/kealeasesync/src os-kealeasesync-1.0.2.pkg
"""

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile

PREFIX = "/usr/local"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_pkg(version, src_dir, output_file):
    # Map source subdirectories to install prefix
    # src_dir/etc/...      -> /usr/local/etc/...
    # src_dir/opnsense/... -> /usr/local/opnsense/...
    files = {}  # install_path -> local_path
    directories = set()
    flatsize = 0

    for subdir in ("etc", "opnsense"):
        local_root = os.path.join(src_dir, subdir)
        if not os.path.isdir(local_root):
            continue
        for dirpath, dirnames, filenames in os.walk(local_root):
            # Register the directory
            rel = os.path.relpath(dirpath, src_dir)
            install_dir = os.path.join(PREFIX, rel)
            directories.add(install_dir)

            for fname in filenames:
                local_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(local_path, src_dir)
                install_path = os.path.join(PREFIX, rel_path)
                files[install_path] = local_path
                flatsize += os.path.getsize(local_path)

    # Read description
    pkg_descr = os.path.join(os.path.dirname(src_dir), "pkg-descr")
    with open(pkg_descr) as f:
        desc = f.read()

    # Files dict: path -> "1$sha256"
    files_dict = {}
    for install_path, local_path in sorted(files.items()):
        files_dict[install_path] = "1$" + sha256_file(local_path)

    # Directories dict: path -> "y" (only plugin-specific dirs, not system dirs)
    dirs_dict = {}
    for d in sorted(directories):
        dirs_dict[d] = "y"

    manifest = {
        "name": "os-kealeasesync",
        "version": version,
        "origin": "net/kealeasesync",
        "comment": "Sync Kea DHCP leases to Unbound DNS",
        "maintainer": "kim@kimlab.ch",
        "www": "https://github.com/c0de-ch/opnsense-plugin-c0de-kimlab",
        "abi": "FreeBSD:*",
        "arch": "freebsd:*",
        "prefix": PREFIX,
        "flatsize": flatsize,
        "desc": desc,
        "categories": ["net"],
        "licenselogic": "single",
        "licenses": ["BSD2CLAUSE"],
        "deps": {
            "unbound": {"origin": "dns/unbound", "version": "0"},
        },
        "files": files_dict,
        "directories": dirs_dict,
        "scripts": {
            "post-install": "service configd restart || true\necho 'os-kealeasesync installed. Configure at Services > Kea Lease Sync.'",
            "post-deinstall": "service configd restart || true",
        },
    }

    compact_manifest = {k: v for k, v in manifest.items() if k not in ("files", "directories", "scripts")}

    # Build tar.zst archive
    # FreeBSD pkg format: +COMPACT_MANIFEST, +MANIFEST, then files at paths relative to /
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        tmp_tar = tmp.name

    with tarfile.open(tmp_tar, "w") as tar:
        # Add +COMPACT_MANIFEST
        cm_data = json.dumps(compact_manifest, indent=2).encode()
        cm_info = tarfile.TarInfo(name="+COMPACT_MANIFEST")
        cm_info.size = len(cm_data)
        tar.addfile(cm_info, fileobj=__import__("io").BytesIO(cm_data))

        # Add +MANIFEST
        m_data = json.dumps(manifest, indent=2).encode()
        m_info = tarfile.TarInfo(name="+MANIFEST")
        m_info.size = len(m_data)
        tar.addfile(m_info, fileobj=__import__("io").BytesIO(m_data))

        # Add files at their absolute install paths (must have leading /)
        # Python's tarfile strips leading / in add() and gettarinfo(),
        # so we build TarInfo manually and force the name after creation.
        for install_path, local_path in sorted(files.items()):
            info = tar.gettarinfo(local_path, arcname=install_path)
            info.name = install_path  # force absolute path with leading /
            with open(local_path, "rb") as f:
                tar.addfile(info, fileobj=f)

    # Compress with zstd
    subprocess.run(["zstd", "-q", "--rm", "-o", output_file, tmp_tar], check=True)

    pkg_size = os.path.getsize(output_file)
    print(f"Built {output_file} ({pkg_size} bytes, {len(files)} files)")

    # Verify: list contents
    print("\nPackage contents:")
    result = subprocess.run(["tar", "-tf", output_file, "--zstd"], capture_output=True, text=True)
    for line in result.stdout.strip().split("\n")[:10]:
        print(f"  {line}")
    remaining = len(result.stdout.strip().split("\n")) - 10
    if remaining > 0:
        print(f"  ... and {remaining} more")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <version> <src-dir> <output-file>")
        sys.exit(1)
    build_pkg(sys.argv[1], sys.argv[2], sys.argv[3])
