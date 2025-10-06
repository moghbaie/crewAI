"""
Utility functions for travel planning system.
Contains helper functions for date handling, location detection, etc.
"""

import datetime
import json
import logging
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


def get_current_date():
    """Get current date in YYYY-MM-DD format"""
    return datetime.datetime.now().strftime("%Y-%m-%d")


async def get_current_location_async():
    """Get current location using IP geolocation asynchronously with error handling."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("http://ip-api.com/json/", timeout=10) as response:
                response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                data = await response.json()
                return {
                    "city": data.get("city", "Unknown"),
                    "region": data.get("regionName", "Unknown"),
                    "country": data.get("country", "Unknown"),
                    "timezone": data.get("timezone", "UTC"),
                    "lat": data.get("lat"),
                    "lon": data.get("lon")
                }
        except asyncio.TimeoutError:
            logger.warning("Location API timeout, using default values.")
        except aiohttp.ClientError as e:
            logger.warning(f"Location API request failed: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode location API response: {e}")
        except Exception as e:
            logger.error(f"Could not detect location: {e}")
        
        return {
            "city": "Unknown",
            "region": "Unknown",
            "country": "Unknown",
            "timezone": "UTC",
            "lat": None,
            "lon": None
        }
