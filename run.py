#!/usr/bin/env python3
"""
Run script for Nicole Web Suite
"""
import sys
import os

# Fix Windows console encoding for emojis - must be done BEFORE any imports
if sys.platform == 'win32':
    # Set environment variable for child processes
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # Reconfigure stdout/stderr for current process
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from app import create_app

if __name__ == '__main__':
    print("[*] Nicole AI Web Suite")
    print("[*] http://127.0.0.1:5000")
    app = create_app()
    app.run(debug=True, host='127.0.0.1', port=5000) 
