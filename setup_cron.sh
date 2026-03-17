#!/usr/bin/env bash
# setup_cron.sh — Install a cron job to run the Morning Brief at 7:00 AM daily
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(command -v python3)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/newsletter.log"
ENV_FILE="$SCRIPT_DIR/.env"

# ── Preflight checks ────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌  .env file not found. Copy .env.example and add your ANTHROPIC_API_KEY:"
  echo "     cp .env.example .env"
  exit 1
fi

if ! grep -q "ANTHROPIC_API_KEY=sk-ant" "$ENV_FILE" 2>/dev/null; then
  echo "⚠️   ANTHROPIC_API_KEY doesn't look set in .env — double-check before running."
fi

# ── Install Python dependencies ─────────────────────────────────────────────
echo "📦  Installing Python dependencies..."
"$PYTHON" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"

# ── Prepare log directory ────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
touch "$LOG_FILE"

# ── Build the cron line ───────────────────────────────────────────────────────
# Runs at 07:00 every day; sources the .env so the API key is available
CRON_CMD="cd \"$SCRIPT_DIR\" && set -a && source .env && set +a && $PYTHON newsletter.py"
CRON_LINE="0 7 * * * $CRON_CMD >> \"$LOG_FILE\" 2>&1"

# ── Install / update cron entry ───────────────────────────────────────────────
CURRENT_CRON="$(crontab -l 2>/dev/null || true)"

if echo "$CURRENT_CRON" | grep -q "newsletter.py"; then
  echo "🔄  Existing cron entry found — replacing it..."
  CURRENT_CRON="$(echo "$CURRENT_CRON" | grep -v 'newsletter.py')"
fi

(echo "$CURRENT_CRON"; echo "$CRON_LINE") | crontab -

echo ""
echo "✅  Cron job installed successfully!"
echo ""
echo "   Schedule : 7:00 AM every day"
echo "   Script   : $SCRIPT_DIR/newsletter.py"
echo "   Logs     : $LOG_FILE"
echo ""
echo "   To run immediately and test:  python3 newsletter.py"
echo "   To view the cron table:       crontab -l"
echo "   To remove the job:            crontab -e  (delete the newsletter line)"
echo ""
