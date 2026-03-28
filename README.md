# opnsense-plugin-c0de-kimlab

Custom OPNsense plugins for the kimlab homelab.

## Plugins

### os-kealeasesync

Syncs Kea DHCP leases and static reservations to Unbound DNS. Each host is registered under:

- **Direct domain** (e.g. `hostname.kimlab.ch`) — real device IP for SSH, ping, direct access
- **Proxy domain(s)** (e.g. `hostname.lab.kim.li`) — reverse proxy IP for HTTPS via Caddy

Includes automatic PTR records, stale record cleanup, and a dashboard widget with table and network map views.

#### Features

- GUI settings page under **Services > Kea Lease Sync**
- Configurable domains, proxy IPs, file paths, TTL, and scan interval
- Configd integration — appears in OPNsense cron dropdown
- Status/hosts/log API endpoints
- Dashboard widget with table view and SVG radial network map
- ARP-based online/offline detection
- Two-tier defaults: safe distribution defaults in model, personal values via gitignored `defaults.conf`

## Install from Release

Download the `.pkg` from the [latest release](https://github.com/c0de-ch/opnsense-plugin-c0de-kimlab/releases/latest) and install directly on OPNsense:

```sh
# On OPNsense (as root):
fetch -o /tmp/os-kealeasesync.pkg \
  https://github.com/c0de-ch/opnsense-plugin-c0de-kimlab/releases/latest/download/os-kealeasesync-1.0.0.pkg
pkg install /tmp/os-kealeasesync.pkg
```

A `.tar.gz` with manual install/uninstall scripts is also available on each release.

## Prerequisites

- OPNsense 24.7+ with **Kea DHCP** and **Unbound DNS** enabled
- `os-caddy` plugin (for reverse proxy domains)
- Root SSH access to OPNsense

## Build from Source

```sh
# Clone
git clone git@github-c0de:c0de-ch/opnsense-plugin-c0de-kimlab.git
cd opnsense-plugin-c0de-kimlab

# Build package
cd net/kealeasesync
make package
# Output: work/pkg/os-kealeasesync-1.0_1.pkg
```

## Install

### Option A: Package install

```sh
# Copy package to OPNsense
scp work/pkg/os-kealeasesync-*.pkg root@<opnsense>:/tmp/

# Install
ssh root@<opnsense>
pkg install /tmp/os-kealeasesync-*.pkg
service configd restart
```

### Option B: Direct deploy (development)

```sh
cd net/kealeasesync
make install DESTDIR=root@<opnsense>:/usr/local
ssh root@<opnsense> "service configd restart"
```

### Apply personal defaults (optional)

```sh
cp net/kealeasesync/defaults.conf.sample net/kealeasesync/defaults.conf
# Edit defaults.conf with your domains and IPs

cd net/kealeasesync
make apply-defaults OPNSENSE_HOST=root@<opnsense>
```

## Configuration

1. Navigate to **Services > Kea Lease Sync**
2. Enable the plugin and configure:
   - **Direct Domain** — domain for real device IPs (e.g. `kimlab.ch`)
   - **Proxy Domains** — space-separated reverse proxy domains (e.g. `lab.kim.li zh.kim.li`)
   - **Proxy IPv4/IPv6** — address of your reverse proxy (Caddy)
   - **DNS TTL** — record TTL in seconds (default 300)
   - **Scan Interval** — sync frequency in minutes
   - File paths (advanced) — Kea lease files and config, pre-filled with standard paths
3. Click **Save**, then **Sync Now** to test

### Add a cron job

**System > Settings > Cron > Add**:
- Command: `Kea Lease DNS Sync`
- Schedule: `*/1 * * * *` (or match your scan interval)

### Enable the dashboard widget

**Lobby > Dashboard > Add Widget > Kea Lease Sync**

The widget shows synced hosts in a table or SVG network map, with online/offline status from the ARP table. Refreshes every 10 seconds.

## Uninstall

```sh
pkg remove os-kealeasesync
```

## File Structure

```
net/kealeasesync/
├── Makefile
├── pkg-descr
├── defaults.conf.sample
└── src/
    ├── etc/inc/plugins.inc.d/kealeasesync.inc
    └── opnsense/
        ├── mvc/app/
        │   ├── controllers/OPNsense/KeaLeaseSync/
        │   │   ├── Api/ServiceController.php
        │   │   ├── Api/SettingsController.php
        │   │   ├── IndexController.php
        │   │   └── forms/general.xml
        │   ├── models/OPNsense/KeaLeaseSync/
        │   │   ├── ACL/ACL.xml
        │   │   ├── Menu/Menu.xml
        │   │   ├── KeaLeaseSync.php
        │   │   └── KeaLeaseSync.xml
        │   └── views/OPNsense/KeaLeaseSync/
        │       └── index.volt
        ├── scripts/OPNsense/KeaLeaseSync/
        │   ├── kea-lease-sync.sh
        │   ├── get_status.py
        │   └── get_hosts.py
        ├── service/
        │   ├── conf/actions.d/actions_kealeasesync.conf
        │   └── templates/OPNsense/KeaLeaseSync/
        │       ├── +TARGETS
        │       └── kealeasesync.conf
        └── www/js/widgets/
            ├── KeaLeaseSync.js
            └── Metadata/KeaLeaseSync.xml
```

## Versioning

This project uses [semantic versioning](https://semver.org/). Releases are built automatically via GitHub Actions when a tag is pushed:

```sh
git tag v1.1.0
git push origin v1.1.0
```

This triggers the release workflow which builds the `.pkg`, distribution tarball, and creates a GitHub Release.

## License

BSD-2-Clause
