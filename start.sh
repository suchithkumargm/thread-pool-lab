#!/usr/bin/env bash
set -e
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use Java 25 (first available ≥21; adjust if needed)
JAVA25=$(/usr/libexec/java_home -v 25 2>/dev/null || /usr/libexec/java_home -v 21 2>/dev/null || /usr/libexec/java_home)
echo "Using Java: $JAVA25"

# Config (override via env: TOMCAT_MAX_THREADS=10 bash start.sh)
export TOMCAT_MAX_THREADS="${TOMCAT_MAX_THREADS:-200}"
export TOMCAT_MIN_THREADS="${TOMCAT_MIN_THREADS:-10}"
export TOMCAT_ACCEPT_COUNT="${TOMCAT_ACCEPT_COUNT:-100}"
export DB_POOL_MAX="${DB_POOL_MAX:-10}"
export DB_POOL_MIN="${DB_POOL_MIN:-2}"
export VIRTUAL_THREADS="${VIRTUAL_THREADS:-false}"

echo "=== Thread Pool Lab (3-instance) ==="
echo "  Thread pool: max=$TOMCAT_MAX_THREADS  min-spare=$TOMCAT_MIN_THREADS  accept-count=$TOMCAT_ACCEPT_COUNT"
echo "  DB pool:     max=$DB_POOL_MAX  min=$DB_POOL_MIN"
echo "  Virtual threads: $VIRTUAL_THREADS"
echo ""

# Kill old instances
pkill -f "thread-pool-lab.*SNAPSHOT.jar" 2>/dev/null || true
pkill -f "proxy.py" 2>/dev/null || true
pkill -f "load_gen.py" 2>/dev/null || true
pkill -f "http.server 3001" 2>/dev/null || true
sleep 1

# Ensure MySQL database exists
echo "1. Checking MySQL database (crud-mysql container)..."
docker exec crud-mysql mysql -uroot -proot -e "CREATE DATABASE IF NOT EXISTS threadpoollab;" 2>/dev/null \
  && echo "   DB ready." \
  || echo "   WARNING: could not create DB — check crud-mysql container is running"

JAR="$BASE/app/target/thread-pool-lab-1.0.0-SNAPSHOT.jar"

echo "2. Starting Spring Boot Instance 1 (port 8080, mgmt 8081)..."
"$JAVA25/bin/java" -jar "$JAR" \
  --server.port=8080 --management.server.port=8081 \
  > /tmp/threadpoollab-app1.log 2>&1 &
echo "   Instance 1 PID: $!"

echo "3. Starting Spring Boot Instance 2 (port 8082, mgmt 8083)..."
"$JAVA25/bin/java" -jar "$JAR" \
  --server.port=8082 --management.server.port=8083 \
  > /tmp/threadpoollab-app2.log 2>&1 &
echo "   Instance 2 PID: $!"

echo "4. Starting Spring Boot Instance 3 (port 8084, mgmt 8085)..."
"$JAVA25/bin/java" -jar "$JAR" \
  --server.port=8084 --management.server.port=8085 \
  > /tmp/threadpoollab-app3.log 2>&1 &
echo "   Instance 3 PID: $!"

echo "   Waiting for all 3 instances to be ready..."
until curl -sf http://localhost:8080/api/fast >/dev/null 2>&1; do sleep 2; done
echo "   Instance 1 ready."
until curl -sf http://localhost:8082/api/fast >/dev/null 2>&1; do sleep 2; done
echo "   Instance 2 ready."
until curl -sf http://localhost:8084/api/fast >/dev/null 2>&1; do sleep 2; done
echo "   Instance 3 ready."

echo "5. Starting reverse proxy (port 8000)..."
cd "$BASE/proxy" && python3 proxy.py > /tmp/threadpoollab-proxy.log 2>&1 &
PROXY_PID=$!
echo "   Proxy PID: $PROXY_PID. Waiting for :8000..."
until curl -sf http://localhost:8000/proxy/health >/dev/null 2>&1; do sleep 1; done
echo "   Proxy ready."
cd "$BASE"

echo "6. Starting load generator (port 8090)..."
cd "$BASE/load-generator" && python3 load_gen.py > /tmp/threadpoollab-lg.log 2>&1 &
LG_PID=$!
sleep 2
echo "   Load generator PID: $LG_PID"
cd "$BASE"

echo "7. Serving dashboard (port 3001)..."
python3 -m http.server 3001 --directory "$BASE/dashboard" > /tmp/threadpoollab-dash.log 2>&1 &
DASH_PID=$!
echo "   Dashboard PID: $DASH_PID"

echo ""
echo "=== All services running ==="
echo "  Proxy (round-robin): http://localhost:8000/api/fast"
echo "  Instance 1:          http://localhost:8080/api/fast  (mgmt: 8081)"
echo "  Instance 2:          http://localhost:8082/api/fast  (mgmt: 8083)"
echo "  Instance 3:          http://localhost:8084/api/fast  (mgmt: 8085)"
echo "  Proxy status:        http://localhost:8000/proxy/status"
echo "  Proxy health:        http://localhost:8000/proxy/health"
echo "  Load gen:            http://localhost:8090/scenarios"
echo "  Dashboard:           http://localhost:3001  ← open this in your browser"
echo ""
echo "Quick test:"
echo "  curl -s http://localhost:8000/api/fast"
echo "  curl -s -X POST http://localhost:8090/run/burst-showcase"
echo ""
echo "Logs: /tmp/threadpoollab-app1.log  /tmp/threadpoollab-app2.log  /tmp/threadpoollab-app3.log"
echo "      /tmp/threadpoollab-proxy.log  /tmp/threadpoollab-lg.log"
echo "Stop: bash $BASE/stop.sh"
echo ""
echo "Press Ctrl+C to stop."
wait
