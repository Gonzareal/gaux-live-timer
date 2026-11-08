#!/bin/bash
# Uso: pluginval_mac.sh <plugin> <nombre> <args de pluginval...>
# Corre pluginval con límite de tiempo y muestra el final del registro si falla o se cuelga.
PLUG="$1"; NAME="$2"; shift 2
PV=pluginval.app/Contents/MacOS/pluginval
"$PV" "$@" --validate "$PLUG" > "pv_$NAME.log" 2>&1 &
P=$!
for i in $(seq 1 120); do sleep 5; kill -0 $P 2>/dev/null || break; done
emit () { msg=$(cut -c1-300 | sed 's/%/%25/g' | awk '{printf "%s%%0A", $0}'); echo "::error title=$1::$msg"; }
if kill -0 $P 2>/dev/null; then
    pkill -9 -f pluginval || true
    tail -n 25 "pv_$NAME.log" | emit "pluginval $NAME: se colgó"
    exit 1
fi
wait $P; rc=$?
grep -q "SUCCESS" "pv_$NAME.log" || rc=1
if [ $rc -ne 0 ]; then tail -n 40 "pv_$NAME.log" | emit "pluginval $NAME: falló"; fi
tail -n 3 "pv_$NAME.log"
exit $rc
