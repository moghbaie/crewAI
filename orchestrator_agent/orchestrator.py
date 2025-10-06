"""
Main orchestration logic for travel planning system.
Handles crew setup, execution, and coordination between agents.
"""

import sys
import logging
from crewai import Crew, Process
from calendar_tools import async_authenticate_google_calendar
from config import setup_langwatch, LANGWATCH_API_KEY, LANGWATCH_AVAILABLE
from utils import get_current_date, get_current_location_async
from agents import (
    create_orchestrator_agent, 
    create_flight_search_agent, 
    create_calendar_agent,
    create_orchestrator_task
)

logger = logging.getLogger(__name__)


async def run_orchestrator(user_travel_request: str) -> None:
    """Main orchestration function that coordinates the entire travel planning workflow."""
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

    # Create agents
    orchestrator_agent = create_orchestrator_agent(user_travel_request, current_date, current_location)
    flight_search_agent = create_flight_search_agent()
    calendar_agent = create_calendar_agent()

    # Create the main collaboration task
    orchestrator_main_collaboration_task = create_orchestrator_task(user_travel_request, orchestrator_agent)

    # Display current context
    print(f"\n📍 Current Location: {current_location['city']}, {current_location['region']}, {current_location['country']}")
    print(f"📅 Current Date: {current_date}")
    print(f"\n✅ Processing Travel Request: {user_travel_request}")

    # Create and configure crew
    crew = Crew(
        agents=[orchestrator_agent, calendar_agent, flight_search_agent],
        tasks=[orchestrator_main_collaboration_task], 
        process=Process.sequential,
        verbose=True
    )

    # Display crew configuration
    print(f"\n--- Crew Configuration ---")
    print(f"Orchestrator Agent LLM: {orchestrator_agent.llm.model}")
    print(f"Flight Search Agent LLM: {flight_search_agent.llm.model}")
    print(f"Calendar Agent LLM: {calendar_agent.llm.model}")
    print(f"Total agents: {len(crew.agents)}")
    print(f"Total tasks: {len(crew.tasks)}")
    print(f"Crew Process: {crew.process}")

    logger.info("Starting crew execution...")
    
    # Execute the crew with optional LangWatch tracing
    if LANGWATCH_AVAILABLE and LANGWATCH_API_KEY:
        import langwatch
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
