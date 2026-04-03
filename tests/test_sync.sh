#!/bin/sh
# test_sync.sh — Tests for kea-lease-sync.sh logic
#
# Tests clean_hostname, lease parsing, state management, and DNS record flow.
# Uses a minimal test harness — no external dependencies.

set -e

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
FAIL_MESSAGES=""

pass() {
    TESTS_RUN=$((TESTS_RUN + 1))
    TESTS_PASSED=$((TESTS_PASSED + 1))
    printf "  PASS: %s\n" "$1"
}

fail() {
    TESTS_RUN=$((TESTS_RUN + 1))
    TESTS_FAILED=$((TESTS_FAILED + 1))
    printf "  FAIL: %s (expected '%s', got '%s')\n" "$1" "$2" "$3"
    FAIL_MESSAGES="${FAIL_MESSAGES}\n  FAIL: $1"
}

assert_eq() {
    _desc="$1" _expected="$2" _actual="$3"
    if [ "$_expected" = "$_actual" ]; then
        pass "$_desc"
    else
        fail "$_desc" "$_expected" "$_actual"
    fi
}

assert_empty() {
    _desc="$1" _actual="$2"
    if [ -z "$_actual" ]; then
        pass "$_desc"
    else
        fail "$_desc" "(empty)" "$_actual"
    fi
}

# ── Load clean_hostname from the sync script ──────────────────
# Extract just the function definition
SCRIPT_DIR="$(cd "$(dirname "$0")/../net/kealeasesync/src/opnsense/scripts/OPNsense/KeaLeaseSync" && pwd)"

# Source only clean_hostname by extracting it
eval "$(sed -n '/^clean_hostname()/,/^}/p' "$SCRIPT_DIR/kea-lease-sync.sh")"

# ══════════════════════════════════════════════════════════════
echo "=== clean_hostname tests ==="
# ══════════════════════════════════════════════════════════════

assert_eq "lowercase conversion" "myhost" "$(clean_hostname 'MyHost')"
assert_eq "all uppercase" "server" "$(clean_hostname 'SERVER')"
assert_eq "strip domain suffix" "myhost" "$(clean_hostname 'myhost.example.com')"
assert_eq "strip trailing dot" "myhost" "$(clean_hostname 'myhost.')"
assert_eq "strip FQDN" "pc" "$(clean_hostname 'pc.home.lan.')"
assert_eq "remove special chars" "myhost" "$(clean_hostname 'my_host!')"
assert_eq "remove underscores" "myhost" "$(clean_hostname 'my_host')"
assert_eq "remove spaces" "mypc" "$(clean_hostname 'my pc')"
assert_eq "hyphens preserved" "my-host" "$(clean_hostname 'my-host')"
assert_eq "numbers preserved" "host123" "$(clean_hostname 'host123')"
assert_eq "mixed case with domain" "server" "$(clean_hostname 'Server.Domain.Com')"
assert_eq "already clean" "myhost" "$(clean_hostname 'myhost')"

# Edge cases
assert_empty "empty string returns empty" "$(clean_hostname '')"
assert_empty "only special chars" "$(clean_hostname '!!!@@@')"
assert_empty "bare MAC (12 hex)" "$(clean_hostname 'aabbccddeeff')"
assert_empty "bare MAC uppercase" "$(clean_hostname 'AABBCCDDEEFF')"
assert_eq "13 hex chars (not MAC)" "aabbccddeeff0" "$(clean_hostname 'aabbccddeeff0')"
assert_eq "11 hex chars (not MAC)" "aabbccddee" "$(clean_hostname 'aabbccddee')"
assert_eq "dhcp-mac prefix kept" "dhcp-aabbccddeeff" "$(clean_hostname 'dhcp-aabbccddeeff')"

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== Kea DHCPv4 lease parsing tests ==="
# ══════════════════════════════════════════════════════════════

TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT

# Create a test lease4 CSV
cat > "$TEST_DIR/leases4.csv" << 'EOF'
address,hwaddr,client_id,valid_lifetime,expire,subnet_id,fqdn_fwd,fqdn_rev,hostname,state,user_context
192.168.1.10,aa:bb:cc:dd:ee:01,,3600,9999999999,1,,,mypc,0,
192.168.1.11,aa:bb:cc:dd:ee:02,,3600,9999999999,1,,,server,0,
192.168.1.12,aa:bb:cc:dd:ee:03,,3600,1,1,,,expired-host,0,
192.168.1.13,aa:bb:cc:dd:ee:04,,3600,9999999999,1,,,,0,
192.168.1.14,aa:bb:cc:dd:ee:05,,3600,9999999999,1,,,declined,2,
EOF

# Parse leases using the same logic as kea-lease-sync.sh
NOW=$(date +%s)
PARSED="$TEST_DIR/parsed.txt"
: > "$PARSED"

tail -n +2 "$TEST_DIR/leases4.csv" | while IFS=, read -r address hwaddr client_id valid_lifetime expire subnet_id fqdn_fwd fqdn_rev hostname state rest; do
    [ "$state" != "0" ] && continue
    if [ -z "$hostname" ] && [ -n "$hwaddr" ]; then
        hostname="dhcp-$(echo "$hwaddr" | tr -d ':')"
    fi
    [ -z "$hostname" ] && continue
    if [ -n "$expire" ] && [ "$expire" -lt "$NOW" ] 2>/dev/null; then
        continue
    fi
    hostname=$(clean_hostname "$hostname") || continue
    echo "A|${hostname}|${address}|dynamic" >> "$PARSED"
done

LEASE_COUNT=$(wc -l < "$PARSED" | tr -d ' ')
assert_eq "parses valid leases" "3" "$LEASE_COUNT"

# Check specific entries
assert_eq "first lease hostname" "A|mypc|192.168.1.10|dynamic" "$(head -1 "$PARSED")"
assert_eq "second lease hostname" "A|server|192.168.1.11|dynamic" "$(sed -n '2p' "$PARSED")"
assert_eq "generates dhcp-mac hostname" "A|dhcp-aabbccddee04|192.168.1.13|dynamic" "$(sed -n '3p' "$PARSED")"

# Verify expired and non-zero state are excluded
if grep -q 'expired-host' "$PARSED"; then
    fail "excludes expired leases" "not present" "found"
else
    pass "excludes expired leases"
fi

if grep -q 'declined' "$PARSED"; then
    fail "excludes non-zero state" "not present" "found"
else
    pass "excludes non-zero state"
fi

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== Kea DHCPv6 lease parsing tests ==="
# ══════════════════════════════════════════════════════════════

cat > "$TEST_DIR/leases6.csv" << 'EOF'
address,duid,valid_lifetime,expire,subnet_id,pref_lifetime,lease_type,iaid,prefix_len,fqdn_fwd,fqdn_rev,hostname,hwaddr,state,user_context
2001:db8::10,01:02:03:04,3600,9999999999,1,3600,0,1,128,,,server6,aa:bb:cc:dd:ee:01,0,
2001:db8::11,01:02:03:05,3600,9999999999,1,3600,0,2,128,,,,aa:bb:cc:dd:ee:02,0,
2001:db8::12,01:02:03:06,3600,9999999999,1,3600,2,3,128,,,prefix-host,,0,
2001:db8::13,01:02:03:07,3600,1,1,3600,0,4,128,,,expired6,,0,
2001:db8::14,01:02:03:08,3600,9999999999,1,3600,0,5,128,,,bad-state,,1,
EOF

PARSED6="$TEST_DIR/parsed6.txt"
: > "$PARSED6"

tail -n +2 "$TEST_DIR/leases6.csv" | while IFS=, read -r address duid valid_lifetime expire subnet_id pref_lifetime lease_type iaid prefix_len fqdn_fwd fqdn_rev hostname hwaddr state rest; do
    [ "$state" != "0" ] && continue
    if [ -z "$hostname" ] && [ -n "$hwaddr" ]; then
        hostname="dhcp-$(echo "$hwaddr" | tr -d ':')"
    elif [ -z "$hostname" ] && [ -n "$duid" ]; then
        hostname="dhcp-$(echo "$duid" | tr -d ':' | tail -c 12)"
    fi
    [ -z "$hostname" ] && continue
    [ "$lease_type" != "0" ] && continue
    if [ -n "$expire" ] && [ "$expire" -lt "$NOW" ] 2>/dev/null; then
        continue
    fi
    hostname=$(clean_hostname "$hostname") || continue
    echo "AAAA|${hostname}|${address}|dynamic" >> "$PARSED6"
done

LEASE6_COUNT=$(wc -l < "$PARSED6" | tr -d ' ')
assert_eq "parses valid IPv6 leases" "2" "$LEASE6_COUNT"
assert_eq "IPv6 lease with hostname" "AAAA|server6|2001:db8::10|dynamic" "$(head -1 "$PARSED6")"
assert_eq "IPv6 generates dhcp-mac" "AAAA|dhcp-aabbccddee02|2001:db8::11|dynamic" "$(sed -n '2p' "$PARSED6")"

if grep -q 'prefix-host' "$PARSED6"; then
    fail "excludes non-zero lease_type" "not present" "found"
else
    pass "excludes non-zero lease_type"
fi

if grep -q 'expired6' "$PARSED6"; then
    fail "excludes expired IPv6 leases" "not present" "found"
else
    pass "excludes expired IPv6 leases"
fi

if grep -q 'bad-state' "$PARSED6"; then
    fail "excludes non-zero state IPv6" "not present" "found"
else
    pass "excludes non-zero state IPv6"
fi

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== Kea DHCPv4 static reservation parsing tests ==="
# ══════════════════════════════════════════════════════════════

cat > "$TEST_DIR/kea-dhcp4.conf" << 'KEAEOF'
{
    "Dhcp4": {
        "subnet4": [
            {
                "subnet": "192.168.1.0/24",
                "reservations": [
                    {"hostname": "printer", "ip-address": "192.168.1.200", "hw-address": "aa:bb:cc:dd:ee:ff"},
                    {"hostname": "nas", "ip-address": "192.168.1.201", "hw-address": "11:22:33:44:55:66"},
                    {"hostname": "", "ip-address": "192.168.1.202", "hw-address": "aa:aa:aa:aa:aa:aa"},
                    {"hostname": "no-ip", "hw-address": "bb:bb:bb:bb:bb:bb"}
                ]
            }
        ]
    }
}
KEAEOF

STATIC_OUT="$TEST_DIR/static4.txt"
python3 -c "
import json
with open('$TEST_DIR/kea-dhcp4.conf') as f:
    cfg = json.load(f)
for subnet in cfg.get('Dhcp4', {}).get('subnet4', []):
    for r in subnet.get('reservations', []):
        hn = r.get('hostname', '')
        ip = r.get('ip-address', '')
        if hn and ip:
            print('A|' + hn + '|' + ip + '|static')
" > "$STATIC_OUT"

STATIC4_COUNT=$(wc -l < "$STATIC_OUT" | tr -d ' ')
assert_eq "parses static reservations" "2" "$STATIC4_COUNT"
assert_eq "first static reservation" "A|printer|192.168.1.200|static" "$(head -1 "$STATIC_OUT")"
assert_eq "second static reservation" "A|nas|192.168.1.201|static" "$(sed -n '2p' "$STATIC_OUT")"

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== Kea DHCPv6 static reservation parsing tests ==="
# ══════════════════════════════════════════════════════════════

cat > "$TEST_DIR/kea-dhcp6.conf" << 'KEA6EOF'
{
    "Dhcp6": {
        "subnet6": [
            {
                "subnet": "2001:db8::/48",
                "reservations": [
                    {"hostname": "server6", "ip-addresses": ["2001:db8::100"], "duid": "01:02:03:04"},
                    {"hostname": "dual-stack", "ip-addresses": ["2001:db8::101", "2001:db8::102"], "duid": "05:06:07:08"},
                    {"hostname": "", "ip-addresses": ["2001:db8::103"], "duid": "09:0a:0b:0c"}
                ]
            }
        ]
    }
}
KEA6EOF

STATIC6_OUT="$TEST_DIR/static6.txt"
python3 -c "
import json
with open('$TEST_DIR/kea-dhcp6.conf') as f:
    cfg = json.load(f)
for subnet in cfg.get('Dhcp6', {}).get('subnet6', []):
    for r in subnet.get('reservations', []):
        hn = r.get('hostname', '')
        for ip in r.get('ip-addresses', []):
            if hn and ip:
                print('AAAA|' + hn + '|' + ip + '|static')
" > "$STATIC6_OUT"

STATIC6_COUNT=$(wc -l < "$STATIC6_OUT" | tr -d ' ')
assert_eq "parses IPv6 static reservations" "3" "$STATIC6_COUNT"
assert_eq "single IPv6 address" "AAAA|server6|2001:db8::100|static" "$(head -1 "$STATIC6_OUT")"
assert_eq "dual-stack first address" "AAAA|dual-stack|2001:db8::101|static" "$(sed -n '2p' "$STATIC6_OUT")"
assert_eq "dual-stack second address" "AAAA|dual-stack|2001:db8::102|static" "$(sed -n '3p' "$STATIC6_OUT")"

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== Dynamic overrides static tests ==="
# ══════════════════════════════════════════════════════════════

MERGE_FILE="$TEST_DIR/merge.txt"
echo "A|printer|192.168.1.200|static" > "$MERGE_FILE"
echo "A|nas|192.168.1.201|static" >> "$MERGE_FILE"

# Simulate dynamic lease overriding static (same logic as sync script)
hostname="printer"
address="192.168.1.50"
sed -i "/^A|${hostname}|/d" "$MERGE_FILE" 2>/dev/null
echo "A|${hostname}|${address}|dynamic" >> "$MERGE_FILE"

assert_eq "dynamic overrides static" "2" "$(wc -l < "$MERGE_FILE" | tr -d ' ')"
if grep -q "192.168.1.200" "$MERGE_FILE"; then
    fail "old static IP removed" "not present" "found"
else
    pass "old static IP removed"
fi
assert_eq "dynamic entry present" "A|printer|192.168.1.50|dynamic" "$(grep 'printer' "$MERGE_FILE")"
assert_eq "other static untouched" "A|nas|192.168.1.201|static" "$(grep 'nas' "$MERGE_FILE")"

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== Stale record detection tests ==="
# ══════════════════════════════════════════════════════════════

# Previous state
PREV_STATE="A|old-host|192.168.1.99|dynamic
A|still-here|192.168.1.10|dynamic
AAAA|gone-v6|2001:db8::99|dynamic"

# Current leases
CURRENT_FILE="$TEST_DIR/current_stale.txt"
echo "A|still-here|192.168.1.10|dynamic" > "$CURRENT_FILE"
echo "A|new-host|192.168.1.50|dynamic" >> "$CURRENT_FILE"

# Find stale records (same logic as sync script)
STALE="$TEST_DIR/stale.txt"
: > "$STALE"
echo "$PREV_STATE" | while IFS='|' read -r rtype hostname ip htype; do
    [ -z "$hostname" ] && continue
    if ! grep -q "^${rtype}|${hostname}|" "$CURRENT_FILE" 2>/dev/null; then
        echo "${rtype}|${hostname}|${ip}|${htype}" >> "$STALE"
    fi
done

STALE_COUNT=$(wc -l < "$STALE" | tr -d ' ')
assert_eq "detects stale records" "2" "$STALE_COUNT"
assert_eq "old-host is stale" "A|old-host|192.168.1.99|dynamic" "$(head -1 "$STALE")"
assert_eq "gone-v6 is stale" "AAAA|gone-v6|2001:db8::99|dynamic" "$(sed -n '2p' "$STALE")"

if grep -q 'still-here' "$STALE"; then
    fail "still-here not stale" "not present" "found"
else
    pass "still-here not stale"
fi

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== PTR record generation tests ==="
# ══════════════════════════════════════════════════════════════

# Test reverse IP generation (same awk logic)
IP="192.168.1.42"
REV=$(echo "$IP" | awk -F. '{print $4"."$3"."$2"."$1}')
assert_eq "reverse IP for PTR" "42.1.168.192" "$REV"

IP2="10.0.0.1"
REV2=$(echo "$IP2" | awk -F. '{print $4"."$3"."$2"."$1}')
assert_eq "reverse IP for 10.x" "1.0.0.10" "$REV2"

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== Hosts JSON generation tests ==="
# ══════════════════════════════════════════════════════════════

HOSTS_JSON=""
while IFS='|' read -r rtype hostname ip htype; do
    [ -z "$hostname" ] && continue
    if [ -n "$HOSTS_JSON" ]; then
        HOSTS_JSON="${HOSTS_JSON},"
    fi
    HOSTS_JSON="${HOSTS_JSON}{\"hostname\":\"${hostname}\",\"ip\":\"${ip}\",\"type\":\"${htype}\",\"rtype\":\"${rtype}\"}"
done << 'JSONEOF'
A|pc1|192.168.1.10|dynamic
AAAA|srv1|2001:db8::10|static
JSONEOF

FULL_JSON="{\"hosts\":[${HOSTS_JSON}]}"
PARSED_COUNT=$(echo "$FULL_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['hosts']))")
assert_eq "hosts JSON has 2 entries" "2" "$PARSED_COUNT"

FIRST_HOST=$(echo "$FULL_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['hosts'][0]['hostname'])")
assert_eq "first host in JSON" "pc1" "$FIRST_HOST"

SECOND_RTYPE=$(echo "$FULL_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['hosts'][1]['rtype'])")
assert_eq "second host rtype" "AAAA" "$SECOND_RTYPE"

# Verify it's valid JSON
if echo "$FULL_JSON" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    pass "hosts JSON is valid"
else
    fail "hosts JSON is valid" "valid JSON" "invalid"
fi

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== Peer host precedence tests ==="
# ══════════════════════════════════════════════════════════════

# Simulate local hosts
PEER_LOCAL="$TEST_DIR/peer_local.txt"
echo "A|myhost|192.168.1.10|dynamic" > "$PEER_LOCAL"
echo "A|server|192.168.1.20|static" >> "$PEER_LOCAL"

# Simulate peer hosts (some overlap with local)
PEER_FILE="$TEST_DIR/peer_remote.txt"
echo "A|myhost|10.0.0.10|peer" > "$PEER_FILE"
echo "A|remote-only|10.0.0.20|peer" >> "$PEER_FILE"
echo "AAAA|remote-v6|2001:db8::99|peer" >> "$PEER_FILE"

# Merge logic: only add peer hosts not already present locally
while IFS='|' read -r rtype hostname ip htype; do
    [ -z "$hostname" ] && continue
    if ! grep -q "^${rtype}|${hostname}|" "$PEER_LOCAL" 2>/dev/null; then
        echo "${rtype}|${hostname}|${ip}|peer" >> "$PEER_LOCAL"
    fi
done < "$PEER_FILE"

PEER_TOTAL=$(wc -l < "$PEER_LOCAL" | tr -d ' ')
assert_eq "peer merge total count" "4" "$PEER_TOTAL"

# myhost should keep its local IP (local takes precedence)
MYHOST_IP=$(grep '^A|myhost|' "$PEER_LOCAL" | head -1 | cut -d'|' -f3)
assert_eq "local host takes precedence over peer" "192.168.1.10" "$MYHOST_IP"

# remote-only should be added
if grep -q 'remote-only' "$PEER_LOCAL"; then
    pass "peer-only host added"
else
    fail "peer-only host added" "present" "not found"
fi

# remote-v6 should be added
if grep -q 'remote-v6' "$PEER_LOCAL"; then
    pass "peer IPv6 host added"
else
    fail "peer IPv6 host added" "present" "not found"
fi

# Test empty peer file
PEER_EMPTY_LOCAL="$TEST_DIR/peer_empty_local.txt"
echo "A|myhost|192.168.1.10|dynamic" > "$PEER_EMPTY_LOCAL"
BEFORE_COUNT=$(wc -l < "$PEER_EMPTY_LOCAL" | tr -d ' ')
PEER_EMPTY="$TEST_DIR/peer_empty.txt"
: > "$PEER_EMPTY"
while IFS='|' read -r rtype hostname ip htype; do
    [ -z "$hostname" ] && continue
    if ! grep -q "^${rtype}|${hostname}|" "$PEER_EMPTY_LOCAL" 2>/dev/null; then
        echo "${rtype}|${hostname}|${ip}|peer" >> "$PEER_EMPTY_LOCAL"
    fi
done < "$PEER_EMPTY"
AFTER_COUNT=$(wc -l < "$PEER_EMPTY_LOCAL" | tr -d ' ')
assert_eq "empty peer file no changes" "$BEFORE_COUNT" "$AFTER_COUNT"

# ══════════════════════════════════════════════════════════════
echo ""
echo "=== Empty lease file tests ==="
# ══════════════════════════════════════════════════════════════

# Only header, no data
cat > "$TEST_DIR/empty_leases4.csv" << 'EOF'
address,hwaddr,client_id,valid_lifetime,expire,subnet_id,fqdn_fwd,fqdn_rev,hostname,state,user_context
EOF

EMPTY_PARSED="$TEST_DIR/empty_parsed.txt"
: > "$EMPTY_PARSED"
tail -n +2 "$TEST_DIR/empty_leases4.csv" | while IFS=, read -r address hwaddr client_id valid_lifetime expire subnet_id fqdn_fwd fqdn_rev hostname state rest; do
    [ "$state" != "0" ] && continue
    [ -z "$hostname" ] && continue
    echo "A|${hostname}|${address}|dynamic" >> "$EMPTY_PARSED"
done

EMPTY_COUNT=$(wc -l < "$EMPTY_PARSED" | tr -d ' ')
assert_eq "empty lease file produces no output" "0" "$EMPTY_COUNT"

# ══════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════"
printf "Results: %d passed, %d failed, %d total\n" "$TESTS_PASSED" "$TESTS_FAILED" "$TESTS_RUN"
echo "═══════════════════════════════════════"

if [ "$TESTS_FAILED" -gt 0 ]; then
    printf "\nFailed tests:%b\n" "$FAIL_MESSAGES"
    exit 1
fi
exit 0
