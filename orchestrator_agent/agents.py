"""
Agent definitions for travel planning system.
Contains all CrewAI agent configurations and their tools.
"""

from crewai import Agent, Task
from calendar_tools import GetAvailabilityTool, CreateCalendarEventTool
from config import initialize_llm, initialize_tools
from models import TravelRequest, AvailableSlot, AIResponse


def create_orchestrator_agent(user_travel_request: str, current_date: str, current_location: dict):
    """Create the main orchestrator agent."""
    llm_instance = initialize_llm()
    
    return Agent(
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
        verbose=True
    )


def create_flight_search_agent():
    """Create the flight search agent."""
    llm_instance = initialize_llm()
    tools = initialize_tools()
    
    return Agent(
        role="Flight Search Agent",
        goal="Find flights and accommodations based on date, budget, and location using Google Search.",
        backstory="Searches for best deals on flights and accommodations from FlightRequest and HotelRequest using the SerpApiGoogleSearchTool.",
        tools=[tools['serp_api_tool']],
        llm=llm_instance,
        verbose=True
    )


def create_calendar_agent():
    """Create the calendar agent."""
    llm_instance = initialize_llm()
    
    return Agent(
        role="Calendar Agent",
        goal="Check calendar availability and create events",
        backstory="Analyzes user's calendar starting from CalendarRequest to find free time and book events using Google Calendar tools.",
        tools=[GetAvailabilityTool(), CreateCalendarEventTool()],
        llm=llm_instance,
        verbose=True
    )


def create_orchestrator_task(user_travel_request: str, orchestrator_agent: Agent):
    """Create the main collaboration task for the orchestrator."""
    tools = initialize_tools()
    
    return Task(
        description=f"""
        **Comprehensive Travel Planning for: {user_travel_request}**

        Your mission is to act as the central coordinator for this travel request.
        Follow these sequential steps to deliver a complete travel plan:
        0.  ** Parse user travel request (Your responsibility):**
            * fill {TravelRequest} by parsing {user_travel_request} using current date as start_date.

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
        tools=[GetAvailabilityTool(), CreateCalendarEventTool(), tools['serp_api_tool']],
        verbose=True
    )
