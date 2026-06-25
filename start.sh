#!/bin/bash
mkdir -p /app/data
chmod 777 /app/data
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
