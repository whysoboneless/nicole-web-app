#!/usr/bin/env python3
"""
Clean run script for Nicole Web Suite - NO VERBOSE STARTUP
"""

import os
import sys
import logging

# Silence ALL logging during startup
logging.disable(logging.CRITICAL)

# Redirect stdout temporarily to suppress Discord bot module noise
class SilentStartup:
    def __enter__(self):
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
        return self
    
    def __exit__(self, *args):
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr

if __name__ == '__main__':
    print("🚀 Nicole AI Web Suite")
    print("📍 http://127.0.0.1:5000")
    
    # Silent startup
    with SilentStartup():
        from app import create_app
        app = create_app()
    
    # Re-enable logging for runtime
    logging.disable(logging.NOTSET)
    
    # Start the app
    app.run(debug=False, host='127.0.0.1', port=5000, use_reloader=False)
