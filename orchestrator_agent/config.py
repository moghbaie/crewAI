"""
Configuration and initialization module for travel planning system.
Handles environment variables, API keys, and LLM setup.
"""

import os
import logging
from functools import lru_cache
from dotenv import load_dotenv

# Optional imports for tracing
try:
    import langwatch
    from openinference.instrumentation.crewai import CrewAIInstrumentor
    LANGWATCH_AVAILABLE = True
except ImportError:
    LANGWATCH_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("LangWatch not available. Tracing will be disabled.")

from crewai import LLM
from crewai_tools import SerpApiGoogleSearchTool

# Initialize Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API Keys
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
LANGWATCH_API_KEY = os.getenv("LANGWATCH_API_KEY")

# Validate required API keys
if not GOOGLE_API_KEY or not SERPAPI_API_KEY:
    logger.warning("Missing API keys! Please set GOOGLE_API_KEY and SERPAPI_API_KEY in your .env file.")
    logger.warning("The application will not work properly without these keys.")
    # Don't raise an error, just warn - this allows the app to start for testing

if not LANGWATCH_API_KEY:
    logger.warning("LANGWATCH_API_KEY not found. LangWatch tracing will be disabled.")


@lru_cache(maxsize=1)
def initialize_llm():
    """Initialize and cache the LLM instance to avoid repeated initializations."""
    try:
        llm = LLM(
            model="gemini/gemini-2.0-flash",
            provider="google",
            api_key=GOOGLE_API_KEY,
            temperature=0.2,  # Add temperature for more reliable responses
            max_tokens=2000  # Limit tokens to prevent timeouts
        )
        logger.info("LLM initialized successfully")
        return llm
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        # Fallback to a more basic configuration
        return LLM(
            model="gemini/gemini-2.0-flash",
            provider="google",
            api_key=GOOGLE_API_KEY
        )


def initialize_tools():
    """Initialize and return all tools used by agents."""
    return {
        'serp_api_tool': SerpApiGoogleSearchTool(api_key=SERPAPI_API_KEY)
    }


def setup_langwatch():
    """Setup LangWatch with CrewAI instrumentation."""
    if LANGWATCH_AVAILABLE and LANGWATCH_API_KEY:
        langwatch.setup(
            instrumentors=[CrewAIInstrumentor()],
            api_key=LANGWATCH_API_KEY
        )
        logger.info("LangWatch tracing enabled with CrewAI instrumentation")
    else:
        logger.warning("LangWatch not available or API key not provided. Tracing disabled.")
