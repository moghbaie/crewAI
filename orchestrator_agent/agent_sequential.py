"""
Legacy agent_sequential.py file - now refactored into modular structure.
This file now imports from the new modular structure for backward compatibility.
"""

# Import all functionality from the new modular structure
from main import main_cli
from orchestrator import run_orchestrator
from models import *
from config import *
from utils import *
from agents import *

# For backward compatibility, expose the main CLI function
if __name__ == "__main__":
    main_cli()
