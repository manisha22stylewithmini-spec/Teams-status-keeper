#!/bin/bash
cd "$(dirname "$0")" && open http://localhost:8765 && python3 server.py
