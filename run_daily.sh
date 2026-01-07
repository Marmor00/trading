#!/bin/bash
# Script para ejecutar daily monitor en PythonAnywhere

cd /home/Marmor00/trading

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Run monitor
python3 daily_monitor.py >> logs/daily_monitor.log 2>&1

# Keep last 100 lines of log
tail -n 100 logs/daily_monitor.log > logs/daily_monitor.log.tmp
mv logs/daily_monitor.log.tmp logs/daily_monitor.log
