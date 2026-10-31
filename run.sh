#!/usr/bin/env bash
# Local runner script for macOS / Linux development
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_EXEC="python3"
else
    echo "Python 3 is required but not found."
    exit 1
fi

echo "🚀 Launching Stock ACB Portfolio Tracker..."
export PYTHONPATH="$DIR:$PYTHONPATH"
exec "$PYTHON_EXEC" -m portfolio_tracker.main "$@"

