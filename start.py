"""
MINIMAL Nicole AI Web Suite startup - ZERO noise
"""
import os
import sys

# Kill ALL output during import
sys.stdout = open(os.devnull, 'w')
sys.stderr = open(os.devnull, 'w')

from app import create_app

# Restore output
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

print("🚀 Nicole AI")
print("📍 localhost:5000")

app = create_app()
app.run(debug=False, host='127.0.0.1', port=5000, use_reloader=False)
