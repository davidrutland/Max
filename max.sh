#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker-compose)
SEARCH_DIR="$ROOT_DIR/search_service"
SEARCH_PYTHON="$SEARCH_DIR/venv/bin/python"
SEARCH_SCRIPT="$SEARCH_DIR/search_service.py"
SEARCH_LOG="$SEARCH_DIR/logs/search_service.log"
PID_FILE="$ROOT_DIR/.max-search-service.pid"
SEARCH_URL="http://127.0.0.1:8787"

log() {
    printf '[max] %s\n' "$*"
}

fail() {
    printf '[max] ERROR: %s\n' "$*" >&2
    exit 1
}

search_health() {
    curl -fsS --max-time 2 "$SEARCH_URL/health" >/dev/null 2>&1
}

pid_is_search_service() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    [[ -r "/proc/$pid/cmdline" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" | grep -Fq -- "$SEARCH_SCRIPT"
}

read_owned_pid() {
    [[ -f "$PID_FILE" ]] || return 1

    local pid
    pid="$(cat "$PID_FILE")"
    pid_is_search_service "$pid" || return 1
    printf '%s\n' "$pid"
}

start_search_service() {
    if search_health; then
        log "search_service already responding on 127.0.0.1:8787; leaving it alone."
        return 0
    fi

    [[ -x "$SEARCH_PYTHON" ]] || fail \
        "search_service environment not found: $SEARCH_PYTHON (run search_service/setup.sh first)."

    [[ -f "$SEARCH_SCRIPT" ]] || fail \
        "search_service script not found: $SEARCH_SCRIPT"

    mkdir -p "$SEARCH_DIR/logs"

    if [[ -f "$PID_FILE" ]]; then
        local stale_pid
        stale_pid="$(cat "$PID_FILE" 2>/dev/null || true)"

        if [[ -n "$stale_pid" ]] && kill -0 "$stale_pid" 2>/dev/null; then
            if pid_is_search_service "$stale_pid"; then
                fail "search_service process $stale_pid is running but /health is not responding."
            fi
        fi

        rm -f "$PID_FILE"
    fi

    log "starting search_service..."
    nohup "$SEARCH_PYTHON" "$SEARCH_SCRIPT" >>"$SEARCH_LOG" 2>&1 &
    local pid=$!

    printf '%s\n' "$pid" > "$PID_FILE"

    for _ in {1..30}; do
        if search_health; then
            log "search_service ready (pid $pid)."
            return 0
        fi

        if ! pid_is_search_service "$pid"; then
            rm -f "$PID_FILE"
            fail "search_service exited during startup; see $SEARCH_LOG"
        fi

        sleep 1
    done

    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"

    fail "search_service did not become healthy within 30 seconds; see $SEARCH_LOG"
}

stop_owned_search_service() {
    local pid

    if ! pid="$(read_owned_pid)"; then
        rm -f "$PID_FILE"

        if search_health; then
            log "search_service is running, but this script does not own it; leaving it alone."
        else
            log "search_service is not running."
        fi

        return 0
    fi

    log "stopping search_service (pid $pid)..."
    kill "$pid" 2>/dev/null || true

    for _ in {1..10}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            log "search_service stopped."
            return 0
        fi

        sleep 1
    done

    log "search_service did not stop gracefully; sending SIGKILL."
    kill -KILL "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
}

start_stack() {
    start_search_service

    log "starting Max containers..."
    if ! "${COMPOSE[@]}" up -d; then
        log "Max startup failed; stopping search_service owned by this script."
        stop_owned_search_service
        exit 1
    fi

    log "Max stack started."
}

stop_stack() {
    local compose_status=0

    log "stopping Max containers..."
    "${COMPOSE[@]}" down || compose_status=$?

    stop_owned_search_service

    if (( compose_status != 0 )); then
        fail "docker-compose down failed with exit code $compose_status."
    fi

    log "Max stack stopped."
}

restart_stack() {
    stop_stack
    start_stack
}

status_stack() {
    printf '===== SEARCH SERVICE =====\n'

    if search_health; then
        local pid

        if pid="$(read_owned_pid)"; then
            printf 'running (owned by max.sh, pid %s)\n' "$pid"
        else
            printf 'running (external process)\n'
        fi
    else
        printf 'stopped\n'
    fi

    printf '\n===== MAX CONTAINERS =====\n'
    "${COMPOSE[@]}" ps
}

usage() {
    cat <<USAGE
Usage: $0 {start|stop|restart|status}

  start    Start search_service if needed, then the Max Docker stack.
  stop     Stop the Max Docker stack and any search_service started by this script.
  restart  Stop and start the complete Max stack.
  status   Show search_service ownership/health and Docker Compose status.
USAGE
}

command="${1:-}"

case "$command" in
    start)
        start_stack
        ;;
    stop)
        stop_stack
        ;;
    restart)
        restart_stack
        ;;
    status)
        status_stack
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
