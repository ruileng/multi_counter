#!/usr/bin/env python3
"""
Multi Counter Web Application - Production Entry Point
Gunicorn + Supervisor + Nginx Deployment Ready
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web_app import create_app

# Create Flask application instance
app = create_app()

if __name__ == "__main__":
    # Development server (not used in production)
    print("🏋️ Multi Counter Web Interface Starting...")
    print("📱 Access at: http://localhost:5000")
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True) 