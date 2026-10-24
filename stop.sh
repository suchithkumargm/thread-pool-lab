#!/usr/bin/env bash
echo "Stopping Thread Pool Lab..."
pkill -f "thread-pool-lab.*SNAPSHOT.jar" 2>/dev/null && echo "  App instances stopped." || echo "  App instances were not running."
pkill -f "proxy.py"                        2>/dev/null && echo "  Proxy stopped."         || echo "  Proxy was not running."
pkill -f "load_gen.py"                     2>/dev/null && echo "  Load gen stopped."      || echo "  Load gen was not running."
pkill -f "http.server 3001"                2>/dev/null && echo "  Dashboard stopped."     || echo "  Dashboard was not running."
echo "Done. (MySQL container left running)"
