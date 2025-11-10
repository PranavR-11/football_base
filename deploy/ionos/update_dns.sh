#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# DNS Auto-Updater for Cloudflare
#
# This script checks if the VPS public IP has changed and updates the
# Cloudflare DNS A record automatically.
#
# Usage:
#   CF_API_TOKEN=xxx ZONE_ID=yyy RECORD_NAME=api.example.com ./update_dns.sh
#
# Environment Variables:
#   CF_API_TOKEN  - Cloudflare API token (required)
#   ZONE_ID       - Cloudflare zone ID (required)
#   RECORD_NAME   - Full DNS record name, e.g., api.example.com (required)
#   TTL           - DNS TTL in seconds (default: 300)
#   PROXIED       - true/false for Cloudflare proxy (default: false)
###############################################################################

# Configuration from environment
CF_API_TOKEN="${CF_API_TOKEN:-}"
ZONE_ID="${ZONE_ID:-}"
RECORD_NAME="${RECORD_NAME:-}"
TTL="${TTL:-300}"
PROXIED="${PROXIED:-false}"

# Cloudflare API endpoint
CF_API="https://api.cloudflare.com/client/v4"

# Log file
LOG_FILE="${LOG_FILE:-/var/log/dns-updater.log}"

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error_exit() {
    log "ERROR: $*"
    echo "{\"ok\":false,\"error\":\"$*\"}"
    exit 1
}

# Validate required variables
[[ -z "$CF_API_TOKEN" ]] && error_exit "CF_API_TOKEN is required"
[[ -z "$ZONE_ID" ]] && error_exit "ZONE_ID is required"
[[ -z "$RECORD_NAME" ]] && error_exit "RECORD_NAME is required"

# Get current public IP
log "Fetching current public IP..."
CURRENT_IP=$(curl -sf https://ipv4.icanhazip.com || curl -sf https://ifconfig.me || curl -sf https://api.ipify.org)

if [[ -z "$CURRENT_IP" ]]; then
    error_exit "Failed to get public IP"
fi

log "Current public IP: $CURRENT_IP"

# Get existing DNS record
log "Fetching DNS record for $RECORD_NAME..."
RECORD_RESPONSE=$(curl -sf -X GET "$CF_API/zones/$ZONE_ID/dns_records?type=A&name=$RECORD_NAME" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json")

if [[ -z "$RECORD_RESPONSE" ]]; then
    error_exit "Failed to fetch DNS record"
fi

# Parse response (requires jq)
RECORD_ID=$(echo "$RECORD_RESPONSE" | jq -r '.result[0].id // empty')
RECORD_IP=$(echo "$RECORD_RESPONSE" | jq -r '.result[0].content // empty')

log "Existing DNS IP: ${RECORD_IP:-none}"

# Check if update is needed
if [[ "$RECORD_IP" == "$CURRENT_IP" ]]; then
    log "DNS record is already up to date"
    echo "{\"ok\":true,\"action\":\"no_change\",\"ip\":\"$CURRENT_IP\"}"
    exit 0
fi

# Prepare JSON payload
UPDATE_JSON=$(jq -n \
    --arg type "A" \
    --arg name "$RECORD_NAME" \
    --arg content "$CURRENT_IP" \
    --argjson ttl "$TTL" \
    --argjson proxied "$PROXIED" \
    '{type:$type, name:$name, content:$content, ttl:$ttl, proxied:$proxied}')

# Update or create record
if [[ -n "$RECORD_ID" ]]; then
    # Update existing record
    log "Updating DNS record $RECORD_ID: $RECORD_IP -> $CURRENT_IP"

    UPDATE_RESPONSE=$(curl -sf -X PUT "$CF_API/zones/$ZONE_ID/dns_records/$RECORD_ID" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$UPDATE_JSON")

    SUCCESS=$(echo "$UPDATE_RESPONSE" | jq -r '.success')

    if [[ "$SUCCESS" == "true" ]]; then
        log "DNS record updated successfully"
        echo "{\"ok\":true,\"action\":\"updated\",\"old_ip\":\"$RECORD_IP\",\"new_ip\":\"$CURRENT_IP\"}"
        exit 0
    else
        ERRORS=$(echo "$UPDATE_RESPONSE" | jq -r '.errors')
        error_exit "Failed to update DNS record: $ERRORS"
    fi
else
    # Create new record
    log "Creating new DNS record for $RECORD_NAME -> $CURRENT_IP"

    CREATE_RESPONSE=$(curl -sf -X POST "$CF_API/zones/$ZONE_ID/dns_records" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$UPDATE_JSON")

    SUCCESS=$(echo "$CREATE_RESPONSE" | jq -r '.success')

    if [[ "$SUCCESS" == "true" ]]; then
        log "DNS record created successfully"
        echo "{\"ok\":true,\"action\":\"created\",\"ip\":\"$CURRENT_IP\"}"
        exit 0
    else
        ERRORS=$(echo "$CREATE_RESPONSE" | jq -r '.errors')
        error_exit "Failed to create DNS record: $ERRORS"
    fi
fi
