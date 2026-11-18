#!/bin/sh
# chakravyuh-ship.sh - Chakravyuh agentless shipper (POSIX sh).
#
# Runs via cron on the client's server. Reads the web server's access log,
# keeps ONLY the lines that match the lure prefix (privacy: real user
# traffic never leaves the host), and sends them HMAC-signed to the
# Chakravyuh server. Installs nothing: it only needs sh, curl, openssl and awk.
#
# Idempotent: stores a byte-offset of the log; the server also deduplicates.
# NEVER modifies or deletes the source log.
#
# Environment variables (see chakravyuh/clients/README.md):
#   CHAKRAVYUH_SERVER     base URL of the Chakravyuh server        (required)
#   CHAKRAVYUH_KEY_ID     sensor key identifier                    (required)
#   CHAKRAVYUH_SECRET     sensor HMAC secret                       (required)
#   CHAKRAVYUH_LOG        access log path                          (required)
#   CHAKRAVYUH_BASE_PATH  lure prefix, e.g. /lure                  (required)
#   CHAKRAVYUH_FORMAT     nginx|apache|caddy|json|raw              (default nginx)
#   CHAKRAVYUH_STATE      offset file                              (default: next to the script)
#   CHAKRAVYUH_DRY_RUN    1 = print what would be sent and exit    (default: empty)
#
# Documented decision: if /control returns enabled=false, nothing is sent and the
# offset is NOT advanced, so no lure lines are lost when the sensor is re-enabled.

LC_ALL=C
export LC_ALL

CAP=20000  # cap on lines per submission (the server also caps at 20000)

die() { printf 'chakravyuh-ship: %s\n' "$*" >&2; exit 1; }
info() { printf 'chakravyuh-ship: %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# 1. Environment and validation
# ---------------------------------------------------------------------------
CHAKRAVYUH_SERVER=${CHAKRAVYUH_SERVER:-}
CHAKRAVYUH_KEY_ID=${CHAKRAVYUH_KEY_ID:-}
CHAKRAVYUH_SECRET=${CHAKRAVYUH_SECRET:-}
CHAKRAVYUH_LOG=${CHAKRAVYUH_LOG:-}
CHAKRAVYUH_BASE_PATH=${CHAKRAVYUH_BASE_PATH:-}
CHAKRAVYUH_FORMAT=${CHAKRAVYUH_FORMAT:-nginx}
CHAKRAVYUH_DRY_RUN=${CHAKRAVYUH_DRY_RUN:-}

[ -n "$CHAKRAVYUH_SERVER" ]    || die "missing CHAKRAVYUH_SERVER"
[ -n "$CHAKRAVYUH_KEY_ID" ]    || die "missing CHAKRAVYUH_KEY_ID"
[ -n "$CHAKRAVYUH_SECRET" ]    || die "missing CHAKRAVYUH_SECRET"
[ -n "$CHAKRAVYUH_LOG" ]       || die "missing CHAKRAVYUH_LOG"
# Empty prefix = ALL traffic would be sent -> forbidden for privacy reasons.
[ -n "$CHAKRAVYUH_BASE_PATH" ] || die "missing CHAKRAVYUH_BASE_PATH (without a prefix, real traffic would be sent)"

CHAKRAVYUH_SERVER=${CHAKRAVYUH_SERVER%/}  # no trailing slash -> avoids //control

command -v curl    >/dev/null 2>&1 || die "curl is not available"
command -v openssl >/dev/null 2>&1 || die "openssl is not available"
command -v awk     >/dev/null 2>&1 || die "awk is not available"

# Directory of the script itself (for the default state).
SELF_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || SELF_DIR=.

# Default state: unique per log path (several logs -> several offsets).
if [ -n "${CHAKRAVYUH_STATE:-}" ]; then
  STATE=$CHAKRAVYUH_STATE
else
  _h=$(printf '%s' "$CHAKRAVYUH_LOG" | cksum 2>/dev/null | cut -d' ' -f1)
  [ -n "$_h" ] || _h=default
  STATE="$SELF_DIR/.chakravyuh-ship-$_h.state"
fi

# ---------------------------------------------------------------------------
# Signature helpers
# ---------------------------------------------------------------------------

# Unix timestamp with decimals (falls back to integers if date does not support %N).
ck_ts() {
  _t=$(date +%s.%N 2>/dev/null)
  case "$_t" in
    *N*|'') _t=$(date +%s) ;;
  esac
  printf '%s' "$_t"
}

# sign_file TS FILE -> "sha256=<hex>" over  TS + "." + <bytes of FILE>
# (identical to chakravyuh.security.sign: HMAC_SHA256(secret, ts.encode()+b"."+body)).
sign_file() {
  _ts=$1; _f=$2
  _hex=$({ printf '%s.' "$_ts"; cat "$_f"; } \
    | openssl dgst -sha256 -hmac "$CHAKRAVYUH_SECRET" 2>/dev/null \
    | awk '{print $NF}')
  [ -n "$_hex" ] || die "openssl failed to compute the HMAC"
  printf 'sha256=%s' "$_hex"
}

# Escapes a short scalar (format / base_path) for JSON.
json_scalar() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

# ---------------------------------------------------------------------------
# Temporales
# ---------------------------------------------------------------------------
TMPD=$(mktemp -d 2>/dev/null) || die "could not create a temporary directory"
trap 'rm -rf "$TMPD"' EXIT INT TERM HUP

RAW="$TMPD/raw"            # new bytes from the log
ESC="$TMPD/esc"            # lure lines already JSON-escaped (one per line)
CNTF="$TMPD/cnt"           # number of lure lines
HDR="$TMPD/hdr"            # /control headers
CBODY="$TMPD/cbody"        # /control body
EMPTY="$TMPD/empty"        # empty body (GET signature)
: > "$EMPTY"

# ---------------------------------------------------------------------------
# 2. Offset + rotation
# ---------------------------------------------------------------------------
[ -e "$CHAKRAVYUH_LOG" ] || die "log does not exist: $CHAKRAVYUH_LOG"
[ -r "$CHAKRAVYUH_LOG" ] || die "no read permission on: $CHAKRAVYUH_LOG"

cur_size=$(wc -c < "$CHAKRAVYUH_LOG" 2>/dev/null | tr -d ' ')
case "$cur_size" in ''|*[!0-9]*) die "could not measure the size of $CHAKRAVYUH_LOG" ;; esac

offset=0
if [ -f "$STATE" ]; then
  offset=$(cat "$STATE" 2>/dev/null)
  case "$offset" in ''|*[!0-9]*) offset=0 ;; esac
fi

# Rotation / truncation: the log shrank -> start from zero.
if [ "$cur_size" -lt "$offset" ]; then
  info "rotation detected ($cur_size < $offset); resetting offset to 0"
  offset=0
fi

if [ "$cur_size" -eq "$offset" ]; then
  info "no new lines (offset $offset)"
  exit 0
fi

# Read only what is new from the offset (tail -c +N is 1-based).
tail -c "+$((offset + 1))" "$CHAKRAVYUH_LOG" > "$RAW" 2>/dev/null \
  || die "could not read $CHAKRAVYUH_LOG from the offset (permissions?)"

# Does it end with a newline? The last line may be mid-write.
NL='
'
ends_nl=0
if [ -s "$RAW" ]; then
  _lc=$(tail -c 1 "$RAW" 2>/dev/null; printf x)
  case "$_lc" in "${NL}x") ends_nl=1 ;; esac
fi

# ---------------------------------------------------------------------------
# 3. Prefix filtering + JSON escaping + count of consumed bytes
#
# consumed = bytes of ALL complete lines (whether they match the prefix or not), so
# the offset advances without reprocessing real traffic. Only lines that CONTAIN
# the prefix are accumulated for sending. The last line without '\n' is left pending.
# ---------------------------------------------------------------------------
: > "$ESC"
consumed=$(awk \
  -v base="$CHAKRAVYUH_BASE_PATH" -v ends_nl="$ends_nl" \
  -v linesfile="$ESC" -v countfile="$CNTF" '
function esc(s,   out, i, c, b, n) {
  out = "\"";
  n = length(s);
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1); b = ordv[c];
    if (c == "\\")      out = out "\\\\";
    else if (c == "\"") out = out "\\\"";
    else if (b == 8)    out = out "\\b";
    else if (b == 9)    out = out "\\t";
    else if (b == 10)   out = out "\\n";
    else if (b == 12)   out = out "\\f";
    else if (b == 13)   out = out "\\r";
    else if (b < 32)    out = out sprintf("\\u%04x", b);
    else                out = out c;
  }
  return out "\"";
}
function flush(line) {
  consumed += length(line) + 1;           # +1 for the terminating \n
  if (index(line, base) > 0) {            # lure lines only
    print esc(line) > linesfile;
    cnt++;
  }
}
BEGIN { for (i = 0; i < 256; i++) ordv[sprintf("%c", i)] = i; consumed = 0; cnt = 0; }
NR > 1 { flush(prev) }                     # prev is always complete
{ prev = $0 }
END {
  if (ends_nl == 1 && NR >= 1) flush(prev);  # last complete line
  print cnt + 0 > countfile;
  print consumed + 0;                        # -> stdout
}
' "$RAW") || die "failed processing the log"

case "$consumed" in ''|*[!0-9]*) consumed=0 ;; esac
cnt=0
if [ -f "$CNTF" ]; then cnt=$(cat "$CNTF" 2>/dev/null); fi
case "$cnt" in ''|*[!0-9]*) cnt=0 ;; esac
newoffset=$((offset + consumed))

# ---------------------------------------------------------------------------
# write_offset: atomic write of the state.
# ---------------------------------------------------------------------------
write_offset() {
  _o=$1
  if ( set -C; printf '%s\n' "$_o" > "$STATE.tmp" ) 2>/dev/null; then
    :
  elif printf '%s\n' "$_o" > "$STATE.tmp" 2>/dev/null; then
    :
  else
    die "could not write state to $STATE (directory permissions?)"
  fi
  mv -f "$STATE.tmp" "$STATE" 2>/dev/null || die "could not update $STATE"
}

# No lure lines in the new data: advance the offset (it was real traffic) and exit.
if [ "$cnt" -eq 0 ]; then
  if [ "$CHAKRAVYUH_DRY_RUN" = "1" ]; then
    info "[dry-run] $consumed new bytes, 0 lure lines; nothing to send (offset $offset -> $newoffset)"
    exit 0
  fi
  write_offset "$newoffset"
  info "0 lure lines; offset $offset -> $newoffset"
  exit 0
fi

fmt_esc=$(json_scalar "$CHAKRAVYUH_FORMAT")
base_esc=$(json_scalar "$CHAKRAVYUH_BASE_PATH")

# Split into batches of up to CAP lines.
CHUNKD="$TMPD/chunks"
mkdir -p "$CHUNKD"
if ! split -l "$CAP" "$ESC" "$CHUNKD/c." 2>/dev/null; then
  cp "$ESC" "$CHUNKD/c.aa"  # fallback: a single batch
fi

# ---------------------------------------------------------------------------
# build_body CHUNK BODYFILE : builds the exact JSON to sign/send.
# ---------------------------------------------------------------------------
build_body() {
  _chunk=$1; _bf=$2
  _arr=$(paste -sd, "$_chunk")
  printf '%s%s%s' \
    '{"format":"'"$fmt_esc"'","base_path":"'"$base_esc"'","lines":[' \
    "$_arr" \
    ']}' > "$_bf"
}

# ---------------------------------------------------------------------------
# 6. DRY-RUN: prints what would be sent and exits (no network, no offset advance).
# ---------------------------------------------------------------------------
if [ "$CHAKRAVYUH_DRY_RUN" = "1" ]; then
  info "[dry-run] server=$CHAKRAVYUH_SERVER format=$CHAKRAVYUH_FORMAT prefix=$CHAKRAVYUH_BASE_PATH"
  info "[dry-run] offset $offset -> $newoffset ; $cnt lure lines (offset NOT advanced)"
  info "[dry-run] skipping /control; the bodies that would be sent follow:"
  _i=0
  for _chunk in "$CHUNKD"/c.*; do
    [ -f "$_chunk" ] || continue
    _i=$((_i + 1))
    _bf="$TMPD/body.$_i"
    build_body "$_chunk" "$_bf"
    _ts=$(ck_ts)
    _sig=$(sign_file "$_ts" "$_bf")
    printf -- '--- batch %s -> POST %s/ingest/logs ---\n' "$_i" "$CHAKRAVYUH_SERVER"
    printf 'X-Chakravyuh-Key-Id: %s\n' "$CHAKRAVYUH_KEY_ID"
    printf 'X-Chakravyuh-Timestamp: %s\n' "$_ts"
    printf 'X-Chakravyuh-Signature: %s\n' "$_sig"
    cat "$_bf"
    printf '\n'
  done
  exit 0
fi

# ---------------------------------------------------------------------------
# 4. GET /control (signed) + verification of the server signature.
# ---------------------------------------------------------------------------
ts=$(ck_ts)
sig=$(sign_file "$ts" "$EMPTY")  # empty body
code=$(curl -sS -o "$CBODY" -D "$HDR" -w '%{http_code}' \
  -H "X-Chakravyuh-Key-Id: $CHAKRAVYUH_KEY_ID" \
  -H "X-Chakravyuh-Timestamp: $ts" \
  -H "X-Chakravyuh-Signature: $sig" \
  "$CHAKRAVYUH_SERVER/control" 2>/dev/null) \
  || die "could not connect to $CHAKRAVYUH_SERVER/control"
[ "$code" = "200" ] || die "/control returned HTTP $code"

srv_ts=$(awk -F': *' 'tolower($1)=="x-chakravyuh-timestamp"{v=$2} END{printf "%s", v}' "$HDR" | tr -d '\r\n')
srv_sig=$(awk -F': *' 'tolower($1)=="x-chakravyuh-server-signature"{v=$2} END{printf "%s", v}' "$HDR" | tr -d '\r\n')
[ -n "$srv_sig" ] || die "/control missing X-Chakravyuh-Server-Signature"

calc=$(sign_file "$srv_ts" "$CBODY")
[ "$calc" = "$srv_sig" ] || die "server signature INVALID (possible MITM); not sending"

enabled=$(sed -n 's/.*"enabled"[[:space:]]*:[[:space:]]*\(true\|false\).*/\1/p' "$CBODY" | head -n1)
if [ "$enabled" != "true" ]; then
  # DECISION: disabled -> do not send and do NOT advance the offset (no lost lure lines).
  info "sensor disabled (enabled=$enabled); nothing sent and offset not advanced ($cnt lines waiting)"
  exit 0
fi

# ---------------------------------------------------------------------------
# 5. POST /ingest/logs in batches (signed). Offset only after full success.
# ---------------------------------------------------------------------------
sent=0
_i=0
for _chunk in "$CHUNKD"/c.*; do
  [ -f "$_chunk" ] || continue
  _i=$((_i + 1))
  _bf="$TMPD/body.$_i"
  build_body "$_chunk" "$_bf"
  _ts=$(ck_ts)
  _sig=$(sign_file "$_ts" "$_bf")
  _resp="$TMPD/resp.$_i"
  code=$(curl -sS -o "$_resp" -w '%{http_code}' -X POST \
    -H "Content-Type: application/json" \
    -H "X-Chakravyuh-Key-Id: $CHAKRAVYUH_KEY_ID" \
    -H "X-Chakravyuh-Timestamp: $_ts" \
    -H "X-Chakravyuh-Signature: $_sig" \
    --data-binary @"$_bf" \
    "$CHAKRAVYUH_SERVER/ingest/logs" 2>/dev/null) \
    || die "network error sending batch $_i (offset not advanced)"
  case "$code" in
    2*) sent=$((sent + 1)) ;;
    *)  die "ingest returned HTTP $code on batch $_i (offset not advanced)" ;;
  esac
done

# All batches OK -> now advance the offset.
write_offset "$newoffset"
info "sent $cnt lure lines in $sent batch(es); offset $offset -> $newoffset"
exit 0
