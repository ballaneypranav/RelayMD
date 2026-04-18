#!/usr/bin/env bash

status_now_utc() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

status_get() {
    local key="$1"
    local line

    [[ -f "${RELAYMD_STATUS_FILE}" ]] || return 0
    line="$(grep -E "^${key}=" "${RELAYMD_STATUS_FILE}" | head -n1 || true)"
    printf '%s' "${line#*=}"
}

status_timestamp_age_seconds() {
    local ts="$1"
    local now epoch

    if [[ -z "${ts}" ]]; then
        printf '%s' "-1"
        return 0
    fi

    now="$(date -u +%s)"
    if ! epoch="$(date -u -d "${ts}" +%s 2>/dev/null)"; then
        printf '%s' "-1"
        return 0
    fi

    printf '%s' "$((now - epoch))"
}

status_port_listening() {
    local port="$1"

    if command -v ss >/dev/null 2>&1; then
        ss -H -ltn "sport = :${port}" 2>/dev/null | grep -q .
        return $?
    fi

    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
        return $?
    fi

    return 1
}

status_tmux_session_alive() {
    local session_name="$1"
    tmux has-session -t "${session_name}" 2>/dev/null
}

status_is_fresh() {
    local timestamp="$1"
    local stale_after="$2"
    local age

    age="$(status_timestamp_age_seconds "${timestamp}")"
    [[ "${age}" -ge 0 && "${age}" -le "${stale_after}" ]]
}

_status_set_pairs_unlocked() {
    local tmp_file key value updated_at updater

    tmp_file="${RELAYMD_STATUS_FILE}.tmp.$$"
    if [[ -f "${RELAYMD_STATUS_FILE}" ]]; then
        cp "${RELAYMD_STATUS_FILE}" "${tmp_file}"
    else
        : > "${tmp_file}"
    fi

    while [[ $# -gt 0 ]]; do
        key="$1"
        value="$2"
        shift 2

        if grep -q -E "^${key}=" "${tmp_file}"; then
            awk -v key="${key}" -v value="${value}" '
                BEGIN { replaced = 0 }
                $0 ~ ("^" key "=") {
                    print key "=" value
                    replaced = 1
                    next
                }
                { print }
                END {
                    if (!replaced) {
                        print key "=" value
                    }
                }
            ' "${tmp_file}" > "${tmp_file}.next"
            mv "${tmp_file}.next" "${tmp_file}"
        else
            printf '%s=%s\n' "${key}" "${value}" >> "${tmp_file}"
        fi
    done

    updated_at="$(status_now_utc)"
    updater="${RELAYMD_EFFECTIVE_USER:-${USER:-unknown}}"

    if grep -q -E '^UPDATED_AT=' "${tmp_file}"; then
        awk -v value="${updated_at}" 'BEGIN { replaced = 0 }
            $0 ~ /^UPDATED_AT=/ {
                print "UPDATED_AT=" value
                replaced = 1
                next
            }
            { print }
            END {
                if (!replaced) {
                    print "UPDATED_AT=" value
                }
            }
        ' "${tmp_file}" > "${tmp_file}.next"
        mv "${tmp_file}.next" "${tmp_file}"
    else
        printf 'UPDATED_AT=%s\n' "${updated_at}" >> "${tmp_file}"
    fi

    if grep -q -E '^UPDATED_BY=' "${tmp_file}"; then
        awk -v value="${updater}" 'BEGIN { replaced = 0 }
            $0 ~ /^UPDATED_BY=/ {
                print "UPDATED_BY=" value
                replaced = 1
                next
            }
            { print }
            END {
                if (!replaced) {
                    print "UPDATED_BY=" value
                }
            }
        ' "${tmp_file}" > "${tmp_file}.next"
        mv "${tmp_file}.next" "${tmp_file}"
    else
        printf 'UPDATED_BY=%s\n' "${updater}" >> "${tmp_file}"
    fi

    mv "${tmp_file}" "${RELAYMD_STATUS_FILE}"
    chmod 664 "${RELAYMD_STATUS_FILE}" 2>/dev/null || true
}

status_set_pairs() {
    local lock_file rc

    if (( $# == 0 || $# % 2 != 0 )); then
        echo "status_set_pairs requires key/value pairs" >&2
        return 1
    fi

    mkdir -p "$(dirname "${RELAYMD_STATUS_FILE}")"
    lock_file="${RELAYMD_STATUS_FILE}.lock"

    if command -v flock >/dev/null 2>&1; then
        exec 9>"${lock_file}"
        flock 9
        if _status_set_pairs_unlocked "$@"; then
            rc=0
        else
            rc=$?
        fi
        flock -u 9
        exec 9>&-
        return "${rc}"
    fi

    _status_set_pairs_unlocked "$@"
}
