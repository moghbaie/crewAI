import os
import datetime
import requests
import click
import json
import sys
import logging
import asyncio
import aiohttp
from typing import List, Optional
from pydantic import BaseModel
from functools import lru_cache
from dotenv import load_dotenv
import langwatch
# from openinference.instrumentation import trace  # Not available in this version
from openinference.instrumentation.crewai import CrewAIInstrumentor
from crewai import Agent, Task, Crew, LLM, Process
from crewai_tools import SerpApiGoogleSearchTool
from calendar_tools import (
    authenticate_google_calendar,
    CreateCalendarEventTool, 
    GetAvailabilityTool,
    async_authenticate_google_calendar # Import the async wrapper for auth
)

# Initialize Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Load Config ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
LANGWATCH_API_KEY = os.getenv("LANGWATCH_API_KEY")

if not GOOGLE_API_KEY or not SERPAPI_API_KEY:
    raise ValueError("Missing API keys! Add them to your .env file.")

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

# --- Initialize Tools ---
serp_api_tool = SerpApiGoogleSearchTool(api_key=SERPAPI_API_KEY)

# Setup LangWatch with CrewAI instrumentation
if LANGWATCH_API_KEY:
    langwatch.setup(
        instrumentors=[CrewAIInstrumentor()],
        api_key=LANGWATCH_API_KEY
    )
    logger.info("LangWatch tracing enabled with CrewAI instrumentation")
else:
    logger.warning("LangWatch API key not provided. Tracing disabled.")

# --- Asynchronous Auto-detection functions ---
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

# --- Pydantic Models ---
class TravelRequest(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    start_date: str
    end_date: str
    duration_min: Optional[int] = None
    duration_max: Optional[int] = None
    number_ptos: Optional[int] = None
    blackout_dates: Optional[List[str]] = None
    priorities: Optional[List[str]] = None
    budget: Optional[float] = None

class CalendarRequest(BaseModel):
    start_date: str            # Earliest possible departure date
    end_date: str              # Latest possible return date
    duration_min: Optional[int] = None  # Minimum days for trip
    duration_max: Optional[int] = None  # Maximum days for trip
    number_ptos : Optional[int]= None
    blackout_dates: Optional[List[str]] = None  # Dates to avoid
    priorities: Optional[List[str]] = None

class AvailableSlot(BaseModel):
    start_date: str            # Start date of available slot
    end_date: str              # End date of available slot
    duration: int              # Number of days
    weekdays_pto_count: int    # Number of PTO days needed for this slot
    notes: Optional[str] = None # Optional comments (e.g., conflicts, weekends)

class CalendarInfo(BaseModel):
    requested_range: CalendarRequest       # Echo back the original request
    available_slots: List[AvailableSlot]   # List of available windows
    errors: Optional[str] = None           # Any error messages encountered 

class FlightRequest(BaseModel):
    origin: str
    destination: str
    outbound_date: str
    return_date: str
    stops: int 
    budget: Optional[float] = None
    travel_class: Optional[str] = "Economy"

class HotelRequest(BaseModel):
    location: str
    check_in_date: str
    check_out_date: str
    budget: Optional[float] = None
    rating_min: Optional[float] = None

class ItineraryRequest(BaseModel):
    destination: str

    check_in_date: str
    check_out_date: str
    flights: Optional[List[FlightRequest]] = None
    hotels: Optional[List[HotelRequest]] = None

class FlightInfo(BaseModel):
    airline: str
    price: float
    duration: str
    stops: int
    departure: str
    arrival: str
    travel_class: str
    flight_number: str
    booking_link: str
    airline_logo: Optional[str] = None

class HotelInfo(BaseModel):
    name: str
    price: float
    rating: float
    location: str
    link: str

class AIResponse(BaseModel):
    available_dates: List[str] = []
    flights: List[FlightInfo] = []
    hotels: List[HotelInfo] = []
    
    ai_flight_recommendation: Optional[str] = ""
    ai_hotel_recommendation: Optional[str] = ""
    itinerary_summary: Optional[str] = ""
    
    top_choice: Optional[dict] = None

# --- Main Orchestration Function (now async) ---
async def run_orchestrator(user_travel_request: str) -> None:
    # Handle exit case
    if user_travel_request.strip().lower() == "exit":
        print("Goodbye!")
        sys.exit(0)

    # Authenticate Google Calendar asynchronously
    credentials = await async_authenticate_google_calendar() 
    if not credentials:
        print("Script cannot proceed without successful authentication.")
        sys.exit(1)

    # Auto-detect current information asynchronously
    current_date = get_current_date()
    current_location = await get_current_location_async()

    # --- Agents ---
    llm_instance = initialize_llm()

    orchestrator_agent = Agent(
        role="Travel Orchestrator Agent",
        goal=f"Coordinate calendar and flight search to find optimal trips for {user_travel_request}",
        backstory=f"""
        Takes {user_travel_request}, detects current date {current_date} and location {current_location['city']}, {current_location['region']}.
        Your core responsibility is to orchestrate the entire travel planning process.
        You will interact with specialized agents (Calendar Agent, Flight Search Agent) by delegating tasks to them.
        You will then synthesize their findings, present curated options to the user, and finally book the chosen trip on their calendar.
        """,
        tools=[], # Orchestrator typically uses other agents/tasks, not direct tools
        llm=llm_instance,
        #allow_delegation=True,
        verbose=True
    )

    flight_search_agent = Agent(
        role="Flight Search Agent",
        goal="Find flights and accommodations based on date, budget, and location using Google Search.",
        backstory=f"Searches for best deals on flights and accommodations from FlightRequest and HotelRequest using the SerpApiGoogleSearchTool.",
        tools=[serp_api_tool],
        llm=llm_instance,
        verbose=True
    )

    calendar_agent = Agent(
        role="Calendar Agent",
        goal="Check calendar availability and create events",
        backstory=f"Analyzes user's calendar starting from CalendarRequest to find free time and book events using Google Calendar tools.",
        tools=[GetAvailabilityTool(), CreateCalendarEventTool()],
        llm=llm_instance,
        verbose=True
    )

    # --- Single Collaboration Task for Orchestrator ---
    print(f"\n📍 Current Location: {current_location['city']}, {current_location['region']}, {current_location['country']}")
    print(f"📅 Current Date: {current_date}")
    print(f"\n✅ Processing Travel Request: {user_travel_request}")

    # This single task now encapsulates the entire workflow for the Orchestrator
    orchestrator_main_collaboration_task = Task(
        description=f"""
        **Comprehensive Travel Planning for: {user_travel_request}**

        Your mission is to act as the central coordinator for this travel request.
        Follow these sequential steps to deliver a complete travel plan:
        0.  ** Parse user travel request (Your responsibility):**
            * fill {TravelRequest} by parsing {user_travel_request} using {current_date} as start_date.

        1.  **Calendar Availability Check (Delegate to Calendar Agent):**
            * First, delegate a task to the 'Calendar Agent' to check the user's Google Calendar for availability.
            * Instruct the 'Calendar Agent' to use {TravelRequest}, considering any specified PTO or blackout dates in the original request.
            * The 'Calendar Agent' must return a JSON list of {AvailableSlot} objects, or a clear error message/indication of no availability.

        2.  **Flight and Accommodation Search (Delegate to Flight Search Agent):**
            * Once you receive {AvailableSlot} from the 'Calendar Agent', delegate a task to the 'Flight Search Agent'.
            * Instruct the 'Flight Search Agent' to search for the best flight and potentially accommodation options from origin to the user's desired destination within budget constraints from {TravelRequest}.
            * The 'Flight Search Agent' must provide a JSON list of {AIResponse} with at least 3 flight options (and optionally hotels) with complete details (price, dates, airline, stops, class, flight number, booking link). If no valid dates are available or no flights found, it should return an appropriate message.

        3.  **Plan Synthesis and Curation (Your responsibility):**
            * Carefully analyze the outputs from both the 'Calendar Agent' and the 'Flight Search Agent'.
            * Synthesize this information to identify the top 3 best travel options that align with the user's request, considering both availability and travel options.
            * For each of the top 3 options, provide:
                * A clear summary of the trip dates.
                * Detailed flight information (airline, price, duration, stops, booking link).
                * A brief explanation of why this option is recommended (e.g., best price, ideal dates, fewest stops).
            * If no viable options can be found due to calendar conflicts or lack of flights, provide a polite and informative message to the user.

        4.  **Present Options and Await User Selection (Human Input):**
            * Present the curated top 3 travel options to the user in a clear, easy-to-read format.
            ** Explicitly ask the user to choose their preferred option (e.g., "Please select option 1, 2, or 3, or type 'none' if you wish to cancel.").
            * **Crucially, this step requires human input and will pause execution until the user responds.**

        5.  **Book Selected Trip (Delegate to Calendar Agent):**
            * Once the user provides their choice, use the 'Create Calendar Event' tool (via the 'Calendar Agent') to book the selected trip in their Google Calendar.
            * Construct an appropriate event summary and description using the details of the chosen trip.
            * Confirm the booking with the user, including the selected trip details and the HTML link to the newly created calendar event.

        Your final output should be a comprehensive summary of the chosen trip and the calendar booking confirmation.
        """,
        expected_output="A final, detailed travel plan for the user's selected option, including flight details and a confirmation message with the Google Calendar event link. If no trip is selected, a cancellation confirmation.",
        agent=orchestrator_agent,
        human_input=True,
        # The orchestrator task directly depends on itself acting as the coordinator
        # Context is implicitly handled by the orchestrator's delegation and analysis steps within its description
        tools=[GetAvailabilityTool(), CreateCalendarEventTool(), serp_api_tool], # The orchestrator has access to all tools to delegate
        verbose=True
    )

    # --- Crew ---
    crew = Crew(
        agents=[orchestrator_agent, calendar_agent, flight_search_agent],
        # Only the orchestrator's main task is directly run by the crew;
        # the orchestrator itself will delegate to other agents/tasks internally.
        tasks=[orchestrator_main_collaboration_task], 
        process=Process.sequential,
        verbose=True
    )

    print(f"\n--- Crew Configuration ---")
    print(f"Orchestrator Agent LLM: {orchestrator_agent.llm.model}")
    print(f"Flight Search Agent LLM: {flight_search_agent.llm.model}")
    print(f"Calendar Agent LLM: {calendar_agent.llm.model}")
    print(f"Total agents: {len(crew.agents)}")
    print(f"Total tasks: {len(crew.tasks)}")
    print(f"Crew Process: {crew.process}")

    logger.info("Starting crew execution...")
    
    # Execute the crew with optional LangWatch tracing
    if LANGWATCH_API_KEY:
        @langwatch.trace(name="CrewAI Travel Planning Workflow")
        def execute_travel_planning():
            result = crew.kickoff()
            if result and str(result).strip():
                print("\n--- Top Travel Options & Booking Result ---")
                print(result)
            return result
        
        execute_travel_planning()
    else:
        # Execute without tracing if LangWatch is not configured
        result = crew.kickoff()
        if result and str(result).strip():
            print("\n--- Top Travel Options & Booking Result ---")
            print(result)

# --- CLI Entrypoint ---
@click.command()
@click.argument("request_args", nargs=-1)
@click.option("--request", "request_opt", help="Travel request string")
def main_cli(request_args: tuple, request_opt: Optional[str]) -> None:
    """CLI entrypoint: pass travel request as positional args or --request option."""
    user_request_text = request_opt or " ".join(request_args).strip()
    if not user_request_text:
        user_request_text = click.prompt("Please enter your travel request (or type 'exit' to quit)")
    
    asyncio.run(run_orchestrator(user_request_text))



# --- Run the CLI ---
if __name__ == "__main__":
    main_cli()
