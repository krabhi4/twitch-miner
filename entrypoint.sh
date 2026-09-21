#!/bin/sh
set -e

if [ -f "/usr/src/app/run.py" ] || [ -f "run.py" ]; then
    exec python run.py "$@"
fi

if [ "$1" = "python" ] && [ "$2" = "run.py" ]; then
    shift 2
    exec python -m TwitchChannelPointsMiner.runner "$@"
fi

if [ "$1" = "sh" ] || [ "$1" = "bash" ] || [ "$1" = "/bin/sh" ] || [ "$1" = "/bin/bash" ]; then
    exec "$@"
fi

exec python -m TwitchChannelPointsMiner.runner "$@"
