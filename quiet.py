import os
import sys
import warnings

# Kill ALL output
warnings.filterwarnings("ignore")
os.environ['PYTHONWARNINGS'] = 'ignore'

# Redirect ALL noise to null
devnull = open(os.devnull, 'w')
sys.stdout = devnull
sys.stderr = devnull

# Import app silently
from app import create_app
app = create_app()

# Restore output
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__
devnull.close()

# Clean startup message
print("🚀 Nicole AI")
print("📍 localhost:5000")

# Start app (silent)
app.run(debug=False, host='127.0.0.1', port=5000, use_reloader=False)
