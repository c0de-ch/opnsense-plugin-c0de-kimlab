PLUGIN_NAME=		kealeasesync
PLUGIN_VERSION=		1.0
PLUGIN_REVISION=	1
PLUGIN_COMMENT=		Sync Kea DHCP leases to Unbound DNS
PLUGIN_MAINTAINER=	kim@c0de.ch
PLUGIN_WWW=		https://github.com/c0de-ch/opnsense-plugin-c0de-kimlab
PLUGIN_DEPENDS=		os-unbound

.include "../../Mk/plugins.mk"

# ── Personal defaults (optional) ─────────────────────────────
# Usage: make apply-defaults OPNSENSE_HOST=root@firewall003
apply-defaults:
	@if [ ! -f defaults.conf ]; then \
		echo "Error: defaults.conf not found. Copy defaults.conf.sample and edit it."; \
		exit 1; \
	fi
	. ./defaults.conf && \
	ssh $(OPNSENSE_HOST) "configctl kealeasesync stop 2>/dev/null; \
		/usr/local/sbin/pluginctl -s kealeasesync set general.directDomain \"$$DIRECT_DOMAIN\"; \
		/usr/local/sbin/pluginctl -s kealeasesync set general.proxyDomains \"$$PROXY_DOMAINS\"; \
		/usr/local/sbin/pluginctl -s kealeasesync set general.proxyIpv4 \"$$PROXY_IPV4\"; \
		/usr/local/sbin/pluginctl -s kealeasesync set general.proxyIpv6 \"$$PROXY_IPV6\"; \
		/usr/local/sbin/pluginctl -s kealeasesync set general.enabled 1; \
		configctl template reload OPNsense/KeaLeaseSync"
	@echo "Defaults applied. Run 'ssh $(OPNSENSE_HOST) configctl kealeasesync run' to test."
