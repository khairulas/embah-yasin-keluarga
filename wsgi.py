"""
WSGI entry point for PythonAnywhere.

In the PythonAnywhere "Web" tab, set this file as the WSGI configuration file
and ensure the working directory points to the project root.
"""
import os
import sys

# Add the project root to sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app import app as application  # noqa: E402,F401
