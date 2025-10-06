import os
import datetime

import json
import sys
import logging
import asyncio
import aiohttp
import chainlit as cl
from typing import List, Optional
from pydantic import BaseModel, Field
from functools import lru_cache
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, LLM, Process
from crewai_tools import SerpApiGoogleSearchTool
from calendar_tools import (
    CreateCalendarEventTool, 
    GetAvailabilityTool,
    async_authenticate_google_calendar,
    CalendarEventRequest
)
import re

# Initialize Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Global variable to store travel options
travel_options = []


# --- Load Config ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

if not GOOGLE_API_KEY or not SERPAPI_API_KEY:
    raise ValueError("Missing API keys! Add them to your .env file.")

@lru_cache(maxsize=1)
def initialize_llm():
    """Initialize and cache the LLM instance to avoid repeated initializations."""
    try:
        llm = LLM(
            model="gemini/gemini-2.0-flash",
            provider="google",
            api_key=GOOGLE_API_KEY,
            temperature=0,  # Add temperature for more reliable responses
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


# --- Function to create and run the Crew, capturing its output ---
async def run_travel_crew_and_capture_output(user_request: str) -> dict:
    """
    Creates and runs the CrewAI travel planning crew, capturing all
    verbose output and returning it along with the final result.
    """
    # Authenticate Google Calendar asynchronously
    credentials = await async_authenticate_google_calendar()
    if not credentials:
        return {"final_result": "Authentication failed.", "logs": "Google Calendar authentication failed."}
    
    current_date = get_current_date()
    current_location = await get_current_location_async()
    llm_instance = initialize_llm() # Ensure LLM is initialized once

    orchestrator_agent = Agent(
        role="Travel Orchestrator Agent",
        goal=f"Coordinate calendar and flight search to find optimal trips for {user_request}",
        backstory=f"""
        Takes {user_request}, detects current date {current_date} and location {current_location['city']}, {current_location['region']}.
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

    orchestrator_main_collaboration_task = Task(
        description=f"""
        **Comprehensive Travel Planning for: {user_request}**

        Your mission is to act as the central coordinator for this travel request.
        Follow these sequential steps to deliver a complete travel plan:
        0.  ** Parse user travel request (Your responsibility):**
            * fill {TravelRequest} by parsing {user_request} using {current_date} as start_date.

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
            * **Your final output MUST be in {TravelOptionsResponse} format containing the top 3 travel options.**
            * IMPORTANT: Each flight option MUST include start_date and end_date as datetime fields in the FlightInformation model for proper calendar integration.
            * If no viable options can be found due to calendar conflicts or lack of flights, provide a polite and informative message to the user.
        
        4.  **Present Options and Get User Choice:**
             * Present the curated top 3 travel options to the user in a clear, easy-to-read format.
             * Present the options in a numbered list (1, 2, 3) with clear descriptions.
             * IMPORTANT: Stop here after presenting the options. Do NOT proceed to booking.
             * Your final output should be the presentation of the 3 options only.
             * ALSO IMPORTANT: You must return the structured AIResponse data in JSON format at the end of your output.

        5.  **Book Selected Trip (Delegate to Calendar Agent):**
            * Once you receive user choice and {TravelOptionsResponse}, use 'CreateCalendarEventTool()' tool (via the 'Calendar Agent') to book the selected trip in their Google Calendar.
            * Construct an appropriate event summary and description using the details of the chosen trip.
            * Confirm the booking with the user, including the selected trip details and the HTML link to the newly created calendar event.

        Your final output should be a comprehensive summary of the chosen trip and the calendar booking confirmation.
        """,
        expected_output="A clear presentation of 3 travel options with detailed information for each option, formatted for user review and selection. MUST include structured TravelOption data  with flight_information and accommodation_information for each option.",
        agent=orchestrator_agent,
        tools=[GetAvailabilityTool(), CreateCalendarEventTool(), serp_api_tool], # The orchestrator has access to all tools to delegate
        verbose=True
    )

    crew = Crew(
        agents=[orchestrator_agent, calendar_agent, flight_search_agent],
        tasks=[orchestrator_main_collaboration_task],
        process=Process.sequential,
        verbose=True
    )
    
    try:
        logger.info("Starting crew execution...")
        
        # Add some debug output
        #print(f"🔍 Debug: Running crew for request: {user_request}")
        
        result = await asyncio.to_thread(crew.kickoff, inputs={
            "user_request": user_request,
            "current_date": current_date,
            "current_location": current_location
        })
        
        #print(f"🔍 Debug: Crew result: {result}")
        #print(f"🔍 Debug: Result type: {type(result)}")
        
        logger.info("Crew execution completed successfully")
        return {
            "final_result": str(result) if result else "No result generated - crew may not have run properly",
            "logs": f"Debug: Request={user_request}, Result={result}"
        }
    except Exception as e:
        logger.error(f"Error running crew: {e}")
        print(f"🔍 Debug: Exception occurred: {e}")
        return {
            "final_result": f"Error: {e}",
            "logs": f"Exception: {e}"
        }

async def create_calendar_event_for_trip(selection: str, travel_options_list: List[dict]) -> str:
    """
    Create a calendar event for the selected travel option using the calendar agent.
    """
    try:
        logger.info(f"Creating calendar event for selection: {selection}")
        logger.info(f"Available travel options: {len(travel_options_list)}")
        
        # Get the selected travel option
        option_num = int(selection)
        if option_num < 1 or option_num > len(travel_options_list):
            return f"Error: Invalid option {selection}. Please select from 1 to {len(travel_options_list)}. Available options: {len(travel_options_list)}"
        
        selected_option = travel_options_list[option_num - 1]
        logger.info(f"Selected option: {selected_option}")
        
        # Use structured data from dictionary (crew output)
        if selected_option:
            logger.info(f"Using structured data from crew output: {selected_option}")
            
            # Create summary from flight data
            summary = f"Trip: {selected_option['flight_information']['airline']} to Paris"
            
            # Parse dates from strings (crew outputs date strings)
            start_date_str = selected_option['flight_information']['start_date']
            end_date_str = selected_option['flight_information']['end_date']
            
            # Convert string dates to datetime objects
            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
            
            logger.info(f"Using dates from crew output: {start_date} to {end_date}")
            
            # Create description with flight and hotel details
            description = f"Flight Details:\n"
            description += f"Airline: {selected_option['flight_information']['airline']}\n"
            description += f"Price: {selected_option['flight_information']['price']}\n"
            description += f"Duration: {selected_option['flight_information'].get('duration', 'N/A')}\n"
            description += f"Stops: {selected_option['flight_information'].get('stops', 'N/A')}\n"
            description += f"Booking Link: {selected_option['flight_information'].get('booking_link', 'N/A')}\n"
            
            description += f"\nHotel Details:\n"
            hotel_name = selected_option['accommodation_information'].get('hotel', selected_option['accommodation_information'].get('hotel_name', 'Hotel'))
            hotel_price = selected_option['accommodation_information'].get('price', selected_option['accommodation_information'].get('price_per_night', 'Price'))
            hotel_link = selected_option['accommodation_information'].get('link', selected_option['accommodation_information'].get('booking_link', 'N/A'))
            
            description += f"Hotel: {hotel_name}\n"
            description += f"Price: {hotel_price}\n"
            description += f"Link: {hotel_link}\n"
            
            description += f"\nRecommendation: {selected_option.get('recommendation', 'N/A')}"
            
        else:
            logger.warning("No structured data available")
            raise ValueError("No structured travel option data found. Cannot create calendar event without proper data.")
        
        # Format dates for the calendar tool (ISO format)
        start_time = start_date.isoformat()
        end_time = end_date.isoformat()
        
        logger.info(f"Creating calendar event: {summary}")
        logger.info(f"Start time: {start_time}, End time: {end_time}")
        logger.info(f"Description: {description}")
        
        # Create CalendarEventRequest object
        event_request = CalendarEventRequest(
            summary=summary,
            description=description,
            start_time=start_time,
            end_time=end_time,
            time_zone="UTC"
        )
        
        # Use the CreateCalendarEventTool to create the event
        calendar_tool = CreateCalendarEventTool()
        result = await calendar_tool._arun(
            summary=summary,
            description=description,
            start_time=start_time,
            end_time=end_time,
            time_zone="UTC"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        return f"Error creating calendar event: {str(e)}"

# --- Pydantic Models for Data Structure ---
# NOTE: The orchestrator agent MUST provide FlightInformation with start_date and end_date
# for proper calendar integration. Expected format:
# {
#   "option_number": 1,
#   "summary": "Trip to Paris",
#   "flight_information": {
#     "airline": "Air France",
#     "price": "$800",
#     "duration": "7h 30m", 
#     "stops": "Direct",
#     "booking_link": "https://...",
#     "start_date": "2025-10-11T09:00:00",  # REQUIRED: ISO datetime string
#     "end_date": "2025-10-16T18:00:00"     # REQUIRED: ISO datetime string
#   },
#   "accommodation_information": {...},
#   "recommendation": "..."
# }

class CrewInput(BaseModel):
    initial_message: str = Field(..., description="Initial message from the person")

class FlightInformation(BaseModel):
    airline: str
    price: str
    duration: str
    stops: str
    booking_link: str
    start_date: datetime.datetime
    end_date: datetime.datetime

class AccommodationInformation(BaseModel):
    hotel: str
    price: str
    link: str

class TravelOption(BaseModel):
    option_number: int
    summary: str
    flight_information: FlightInformation
    accommodation_information: AccommodationInformation
    recommendation: str

class TravelOptionsResponse(BaseModel):
    options: List[TravelOption]

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


# --- Function to create and run the Crew, capturing its output ---
async def run_travel_crew_and_capture_output(user_request: str) -> dict:
    """
    Creates and runs the CrewAI travel planning crew, capturing all
    verbose output and returning it along with the final result.
    """
    # Authenticate Google Calendar asynchronously
    credentials = await async_authenticate_google_calendar()
    if not credentials:
        return {"final_result": "Authentication failed.", "logs": "Google Calendar authentication failed."}
    
    current_date = get_current_date()
    current_location = await get_current_location_async()
    llm_instance = initialize_llm() # Ensure LLM is initialized once

    orchestrator_agent = Agent(
        role="Travel Orchestrator Agent",
        goal=f"Coordinate calendar and flight search to find optimal trips for {user_request}",
        backstory=f"""
        Takes {user_request}, detects current date {current_date} and location {current_location['city']}, {current_location['region']}.
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

    orchestrator_main_collaboration_task = Task(
        description=f"""
        **Comprehensive Travel Planning for: {user_request}**

        Your mission is to act as the central coordinator for this travel request.
        Follow these sequential steps to deliver a complete travel plan:
        0.  ** Parse user travel request (Your responsibility):**
            * fill {TravelRequest} by parsing {user_request} using {current_date} as start_date.

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
            * **Your final output MUST be in {TravelOptionsResponse} format containing the top 3 travel options.**
            * **CRITICAL: You must output a JSON object with "options" as the key, not just an array.**
            * **Example structure: {{ "options": [your_travel_options_array] }}**
            * If no viable options can be found due to calendar conflicts or lack of flights, provide a polite and informative message to the user.

        4.  **Present Options and Get User Choice:**
             * Present the 3 travel options in a human-readable format with clear descriptions.
             * Present the options in a numbered list (1, 2, 3) with clear descriptions.
             * IMPORTANT: Stop here after presenting the options. Do NOT proceed to booking.
             * Your final output should be the presentation of the 3 options only.
             * ALSO IMPORTANT: You must return the structured TravelOptionsResponse data in JSON format at the end of your output.

        5.  **Book Selected Trip (Delegate to Calendar Agent):**
            * Once you receive user choice and JSON list of {TravelOption} objects, use 'CreateCalendarEventTool()' tool (via the 'Calendar Agent') to book the selected trip in their Google Calendar.
            * Construct an appropriate event summary and description using the details of the chosen trip.
            * Confirm the booking with the user, including the selected trip details and the HTML link to the newly created calendar event.

        Your final output should be a comprehensive summary of the chosen trip and the calendar booking confirmation.
        """,
        expected_output="A clear presentation of 3 travel options with detailed information for each option, formatted for user review and selection. MUST include structured TravelOptionsResponse data in JSON format with 'options' key containing TravelOption objects, each with flight_information (including start_date and end_date) and accommodation_information.",
        agent=orchestrator_agent,
        tools=[GetAvailabilityTool(), CreateCalendarEventTool(), serp_api_tool], # The orchestrator has access to all tools to delegate
        verbose=True
    )

    crew = Crew(
        agents=[orchestrator_agent, calendar_agent, flight_search_agent],
        tasks=[orchestrator_main_collaboration_task],
        process=Process.sequential,
        verbose=True
    )
    
    try:
        logger.info("Starting crew execution...")
        
        # Add some debug output
        #print(f"🔍 Debug: Running crew for request: {user_request}")
        
        result = await asyncio.to_thread(crew.kickoff, inputs={
            "user_request": user_request,
            "current_date": current_date,
            "current_location": current_location
        })
        
        #print(f"🔍 Debug: Crew result: {result}")
        #print(f"🔍 Debug: Result type: {type(result)}")
        
        logger.info("Crew execution completed successfully")
        return {
            "final_result": str(result) if result else "No result generated - crew may not have run properly",
            "logs": f"Debug: Request={user_request}, Result={result}"
        }
    except Exception as e:
        logger.error(f"Error running crew: {e}")
        print(f"🔍 Debug: Exception occurred: {e}")
        return {
            "final_result": f"Error: {e}",
            "logs": f"Exception: {e}"
        }

@cl.on_chat_start
async def on_chat_start():
    await cl.Message(content="Hello I am your personal Assistant. How can I help?").send()

@cl.on_message
async def on_message(message: cl.Message):
    user_travel_request = message.content # Directly use message content

    if user_travel_request.strip().lower() == "exit":
        await cl.Message(content="Goodbye!").send()
        sys.exit(0)

    # Check if this is a user selection (1, 2, 3) or a new travel request
    if user_travel_request.strip() in ['1', '2', '3']:
        # This is a user selection - handle the booking
        await handle_user_selection(user_travel_request)
        return

    # This is a new travel request - start the planning process
    await cl.Message(content=f"🚀 Starting travel planning for: **{user_travel_request}**").send()

    try:
        # Run the first phase: present options
        orchestrator_output = await run_travel_crew_and_capture_output(user_travel_request)
        final_result_raw = orchestrator_output["final_result"]
        logger.info(f"final_result_raw: {final_result_raw}")
        
        # Extract JSON from the output (crew outputs both text + JSON)
        if "```json" in final_result_raw:
            # Find the JSON section (it's at the end)
            json_start = final_result_raw.find("```json")
            json_end = final_result_raw.find("```", json_start + 7)  # +7 to skip "```json"
            
            if json_start != -1 and json_end != -1:
                # Extract just the JSON part
                json_content = final_result_raw[json_start + 7:json_end].strip()
                logger.info(f"Extracted JSON content: {json_content[:200]}...")
                
                try:
                    # Parse the JSON object with "options" key
                    global travel_options
                    parsed_data = json.loads(json_content)
                    
                    # Handle both formats: direct array or {"options": [...]}
                    if isinstance(parsed_data, list):
                        travel_options = parsed_data
                        logger.info(f"Successfully parsed {len(travel_options)} TravelOption objects from array")
                    elif isinstance(parsed_data, dict) and "options" in parsed_data:
                        travel_options = parsed_data["options"]
                        logger.info(f"Successfully parsed {len(travel_options)} TravelOption objects from options key")
                    else:
                        logger.error(f"Unexpected format: {type(parsed_data)}")
                        travel_options = []
                    
                    # Step 4: Present options in human-readable format
                    if travel_options:
                        option_count = len(travel_options)
                        
                        # Create human-readable display of TravelOption objects
                        display_options = ""
                        for i, option in enumerate(travel_options, 1):
                            # Handle both expected format and actual crew output
                            summary = option.get('summary', option.get('trip_dates', 'Trip'))
                            airline = option['flight_information']['airline']
                            price = option['flight_information']['price']
                            hotel = option['accommodation_information'].get('hotel', option['accommodation_information'].get('hotel_name', 'Hotel'))
                            hotel_price = option['accommodation_information'].get('price', option['accommodation_information'].get('price_per_night', 'Price'))
                            start_date = option['flight_information']['start_date']
                            end_date = option['flight_information']['end_date']
                            origin_airport = option['flight_information']['origin']
                            destination_airport = option['flight_information']['destination']
                            stops = option['flight_information']['stops']
                            duration = option['flight_information']['duration']
                            
                            display_options += f"**Option {i}:** {summary}\n"
                            display_options += f"  Flight: {airline} - ${price}\n"
                            display_options += f"  Hotel: {hotel} - ${hotel_price}\n"
                            display_options += f"  Dates: {start_date} to {end_date}\n\n"
                            
                        
                        # Dynamic prompt based on number of options
                        if option_count == 1:
                            message_content = f"**🎯 Here is your travel option:**\n\n{display_options}\n**Please select option 1:**"
                        elif option_count == 2:
                            message_content = f"**🎯 Here are your travel options:**\n\n{display_options}\n**Please select option 1 or 2:**"
                        elif option_count == 3:
                            message_content = f"**🎯 Here are your travel options:**\n\n{display_options}\n**Please select option 1, 2, or 3:**"
                        else:
                            message_content = f"**🎯 Here are your travel options:**\n\n{display_options}\n**Please select option 1, 2, or 3:**"
                        
                        await cl.Message(content=message_content).send()
                    else:
                        await cl.Message(content="⚠️ No travel options were generated.").send()
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing failed: {e}")
                    await cl.Message(content="❌ Error parsing travel options. Please try again.").send()
            else:
                await cl.Message(content="❌ Could not extract travel options from crew output.").send()
        else:
            await cl.Message(content="❌ No structured travel data found in crew output.").send()

    except Exception as e:
        logger.error(f"Error during trip planning: {e}", exc_info=True)
        await cl.Message(content=f"❌ An error occurred during trip planning: {str(e)}").send()

async def handle_user_selection(selection: str):
    """Handle user's selection and proceed with booking"""
    await cl.Message(content=f"✅ You selected option {selection}. Proceeding with booking...").send()
    
    try:
        # Create the calendar event using the calendar agent
        calendar_result = await create_calendar_event_for_trip(selection, travel_options)
        
        if "Error" in calendar_result:
            await cl.Message(content=f"❌ {calendar_result}").send()
        else:
            await cl.Message(
                content=f"**🎉 Booking confirmed for option {selection}!**\n\n"
                        f"Your trip has been booked and added to your Google Calendar.\n\n"
                        f"**Calendar Event Details:**\n{calendar_result}"
            ).send()
            
    except Exception as e:
        logger.error(f"Error during booking: {e}")
        await cl.Message(content=f"❌ An error occurred during booking: {str(e)}").send()


# Add main execution block for running as regular Python script
if __name__ == "__main__":
    async def main():
        # Test the travel planning system
        print("🚀 Starting Travel Planning System...")
        print("📝 This is a TEST run - not using Chainlit interface")
        
        # Test with a sample travel request
        sample_request = "I want to plan a trip to Paris for next month, around 5-7 days"
        print(f"\n🧳 Testing with sample request: {sample_request}")
        
        # Run the crew and capture results
        print("🚀 Running crew...")
        result = await run_travel_crew_and_capture_output(sample_request)
        
        print(f"\n✅ Final Result: {result.get('final_result', 'No result')}")
        if result.get('logs'):
            print(f"\n📋 Logs: {result['logs']}")
        
        print("\n🏁 Test completed. To use the full interface, run: chainlit run orchestrator_agent/app.py")
        
    # Run the async main function
    asyncio.run(main())
else:
    # This code runs when imported by Chainlit
    print("🔗 Chainlit mode activated - travel planning system ready for web interface")
