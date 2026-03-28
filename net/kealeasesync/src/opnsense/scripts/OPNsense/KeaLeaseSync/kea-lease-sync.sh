#!/bin/sh
# kea-lease-sync.sh — Sync Kea DHCP leases + static reservations to Unbound DNS
#
# Order: static reservations loaded first, dynamic leases override if present
# (lease reflects the actual current IP the device is using)
#
# Registers each host under:
#   hostname.<directDomain>     → real device IP (SSH, ping, direct)
#   hostname.<proxyDomain(s)>   → proxy/Caddy IP (HTTPS reverse proxy)

# ── Configuration ────────────────────────────────────────────
CONF_FILE="/usr/local/etc/kealeasesync/kealeasesync.conf"
RUN_DIR="/var/run/kealeasesync"
STATE_FILE="${RUN_DIR}/kea-lease-sync.state"
STATUS_FILE="${RUN_DIR}/status.json"
HOSTS_FILE="${RUN_DIR}/hosts.json"
UNBOUND_CONF="/var/unbound/unbound.conf"
LOG_TAG="kea-lease-sync"

# Read generated config
if [ ! -f "$CONF_FILE" ]; then
    logger -t "$LOG_TAG" -p daemon.err "Config file not found: $CONF_FILE"
    exit 1
fi
. "$CONF_FILE"

# Check if enabled
if [ "$ENABLED" != "1" ]; then
    logger -t "$LOG_TAG" -p daemon.info "Sync disabled, skipping"
    exit 0
fi

# Validate required fields
if [ -z "$DIRECT_DOMAIN" ]; then
    logger -t "$LOG_TAG" -p daemon.err "directDomain not configured"
    exit 1
fi
# ─────────────────────────────────────────────────────────────

log_info()  { logger -t "$LOG_TAG" -p daemon.info  "$1"; }
log_err()   { logger -t "$LOG_TAG" -p daemon.err   "$1"; }

uc() {
    /usr/local/sbin/unbound-control -c "$UNBOUND_CONF" "$@"
}

# Ensure run directory exists
mkdir -p "$RUN_DIR"

START_TIME=$(date +%s)

if ! uc status >/dev/null 2>&1; then
    log_err "unbound-control not responding"
    exit 1
fi

# Ensure local zones exist
uc local_zone "${DIRECT_DOMAIN}." static 2>/dev/null
for pd in $PROXY_DOMAINS; do
    uc local_zone "${pd}." static 2>/dev/null
done

NOW=$(date +%s)
STATIC_LEASES="${RUN_DIR}/sync.static.$$"
CURRENT_LEASES="${RUN_DIR}/sync.current.$$"
: > "$STATIC_LEASES"
: > "$CURRENT_LEASES"
trap 'rm -f "$STATIC_LEASES" "$CURRENT_LEASES"' EXIT

# ── Helper: clean hostname ───────────────────────────────────
clean_hostname() {
    _h="$1"
    _h=$(echo "$_h" | sed 's/\..*$//;s/\.$//')
    _h=$(echo "$_h" | tr 'A-Z' 'a-z')
    _h=$(echo "$_h" | sed 's/[^a-z0-9-]//g')
    [ -z "$_h" ] && return 1
    # Skip bare MAC-like hostnames (12 hex chars)
    case "$_h" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f])
            return 1 ;;
    esac
    echo "$_h"
    return 0
}

# ── Step 1: Parse Kea static reservations → STATIC_LEASES ───
STATIC_COUNT=0
if [ -f "$KEA_CONF" ]; then
    awk '
        /"ip-address"/ { gsub(/[",]/, ""); split($0, a, ":"); ip=a[2]; gsub(/ /, "", ip) }
        /"hostname"/ { gsub(/[",]/, ""); split($0, a, ":"); hn=a[2]; gsub(/ /, "", hn); if (ip != "" && hn != "") print "A|" hn "|" ip "|static"; ip=""; hn="" }
    ' "$KEA_CONF" >> "$STATIC_LEASES"
    STATIC_COUNT=$(wc -l < "$STATIC_LEASES" | tr -d ' ')
fi

# Start with static reservations
cp "$STATIC_LEASES" "$CURRENT_LEASES"

# ── Step 2: Parse IPv4 leases — override static if present ──
DYNAMIC_COUNT=0
if [ -f "$LEASE4_FILE" ]; then
    tail -n +2 "$LEASE4_FILE" | while IFS=, read -r address hwaddr client_id valid_lifetime expire subnet_id fqdn_fwd fqdn_rev hostname state rest; do
        [ -z "$hostname" ] && continue
        [ "$state" != "0" ] && continue
        if [ -n "$expire" ] && [ "$expire" -lt "$NOW" ] 2>/dev/null; then
            continue
        fi
        hostname=$(clean_hostname "$hostname") || continue
        # Remove static entry if exists (lease overrides)
        sed -i '' "/^A|${hostname}|/d" "$CURRENT_LEASES" 2>/dev/null
        echo "A|${hostname}|${address}|dynamic" >> "$CURRENT_LEASES"
    done
    DYNAMIC_COUNT=$(grep -c '|dynamic$' "$CURRENT_LEASES" 2>/dev/null || echo 0)
fi

# ── Step 3: Parse IPv6 leases ────────────────────────────────
if [ -f "$LEASE6_FILE" ]; then
    tail -n +2 "$LEASE6_FILE" | while IFS=, read -r address duid valid_lifetime expire subnet_id pref_lifetime lease_type iaid prefix_len fqdn_fwd fqdn_rev hostname hwaddr state rest; do
        [ -z "$hostname" ] && continue
        [ "$state" != "0" ] && continue
        [ "$lease_type" != "0" ] && continue
        if [ -n "$expire" ] && [ "$expire" -lt "$NOW" ] 2>/dev/null; then
            continue
        fi
        hostname=$(clean_hostname "$hostname") || continue
        echo "AAAA|${hostname}|${address}|dynamic" >> "$CURRENT_LEASES"
    done
fi

# ── Load previous state ──────────────────────────────────────
PREVIOUS_LEASES=""
if [ -f "$STATE_FILE" ]; then
    PREVIOUS_LEASES=$(cat "$STATE_FILE")
fi

# ── Add/update records ───────────────────────────────────────
ADDED=0
HOSTS_JSON=""
if [ -s "$CURRENT_LEASES" ]; then
    while IFS='|' read -r rtype hostname ip htype; do
        [ -z "$hostname" ] && continue
        [ -z "$ip" ] && continue

        hostname=$(clean_hostname "$hostname") || continue

        # Direct domain — real device IP
        uc local_data "${hostname}.${DIRECT_DOMAIN}. ${TTL} IN ${rtype} ${ip}" 2>/dev/null

        # Proxy domains — Caddy IP
        for pd in $PROXY_DOMAINS; do
            if [ "$rtype" = "A" ]; then
                uc local_data "${hostname}.${pd}. ${TTL} IN A ${PROXY_IPV4}" 2>/dev/null
            elif [ "$rtype" = "AAAA" ]; then
                uc local_data "${hostname}.${pd}. ${TTL} IN AAAA ${PROXY_IPV6}" 2>/dev/null
            fi
        done

        # PTR for direct domain only (IPv4)
        if [ "$rtype" = "A" ]; then
            REV=$(echo "$ip" | awk -F. '{print $4"."$3"."$2"."$1}')
            uc local_data "${REV}.in-addr.arpa. ${TTL} IN PTR ${hostname}.${DIRECT_DOMAIN}." 2>/dev/null
        fi

        # Build JSON hosts array
        if [ -n "$HOSTS_JSON" ]; then
            HOSTS_JSON="${HOSTS_JSON},"
        fi
        HOSTS_JSON="${HOSTS_JSON}{\"hostname\":\"${hostname}\",\"ip\":\"${ip}\",\"type\":\"${htype}\",\"rtype\":\"${rtype}\"}"

        ADDED=$((ADDED + 1))
    done < "$CURRENT_LEASES"
fi

# ── Remove stale records ─────────────────────────────────────
REMOVED=0
if [ -n "$PREVIOUS_LEASES" ]; then
    echo "$PREVIOUS_LEASES" | while IFS='|' read -r rtype hostname ip htype; do
        [ -z "$hostname" ] && continue
        if ! grep -q "^${rtype}|${hostname}|" "$CURRENT_LEASES" 2>/dev/null; then
            uc local_data_remove "${hostname}.${DIRECT_DOMAIN}." 2>/dev/null
            for pd in $PROXY_DOMAINS; do
                uc local_data_remove "${hostname}.${pd}." 2>/dev/null
            done
            if [ "$rtype" = "A" ]; then
                REV=$(echo "$ip" | awk -F. '{print $4"."$3"."$2"."$1}')
                uc local_data_remove "${REV}.in-addr.arpa." 2>/dev/null
            fi
            REMOVED=$((REMOVED + 1))
            log_info "Removed stale: ${hostname} (${rtype} ${ip})"
        fi
    done
fi

# Save state
cp "$CURRENT_LEASES" "$STATE_FILE" 2>/dev/null

# Recount after subshell processing
STATIC_COUNT=$(grep -c '|static$' "$CURRENT_LEASES" 2>/dev/null || echo 0)
DYNAMIC_COUNT=$(grep -c '|dynamic$' "$CURRENT_LEASES" 2>/dev/null || echo 0)

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Write status JSON
cat > "$STATUS_FILE" <<STATUSEOF
{
    "status": "ok",
    "last_sync": "$(date -r "$END_TIME" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')",
    "hosts_registered": ${ADDED},
    "hosts_removed": ${REMOVED},
    "static_count": ${STATIC_COUNT},
    "dynamic_count": ${DYNAMIC_COUNT},
    "duration": "${DURATION}s",
    "direct_domain": "${DIRECT_DOMAIN}",
    "proxy_domains": "${PROXY_DOMAINS}"
}
STATUSEOF

# Write hosts JSON
cat > "$HOSTS_FILE" <<HOSTSEOF
{"hosts":[${HOSTS_JSON}]}
HOSTSEOF

log_info "Sync done: ${ADDED} registered, ${REMOVED} removed (${STATIC_COUNT} static, ${DYNAMIC_COUNT} dynamic) in ${DURATION}s"
