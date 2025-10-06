import os.path
from pathlib import Path
import asyncio
import pytz
import os
import webbrowser
from dotenv import load_dotenv
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from crewai.tools import BaseTool
from typing import Type, Optional, List
from pydantic import BaseModel, Field
import pickle
from functools import lru_cache

load_dotenv()

# If modifying these scopes, delete the file token.json.
# This scope allows full read/write access to your Google Calendar.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Pydantic model for calendar event creation
class CalendarEventRequest(BaseModel):
    """Model for creating calendar events"""
    summary: str = Field(..., description="Event title/summary")
    description: str = Field(..., description="Event description")
    start_time: str = Field(..., description="Start time in ISO format (YYYY-MM-DDTHH:MM:SS)")
    end_time: str = Field(..., description="End time in ISO format (YYYY-MM-DDTHH:MM:SS)")
    time_zone: str = Field(default="UTC", description="Time zone for the event")
    attendees: Optional[List[str]] = Field(default=None, description="List of attendee email addresses")
    calendar_id: str = Field(default="primary", description="Calendar ID to create event in")

def authenticate_google_calendar():
    """
    Authenticates with Google Calendar API using a manual (out-of-band) flow.
    If a valid token.json exists, it uses that; otherwise, it prompts for new
    authentication. This remains a synchronous function as it involves user input.
    """
    creds = None
    # Resolve paths relative to this file's directory (calendar_agent/)
    base_dir = Path(__file__).parent
    token_path = base_dir / "token.json"
    client_secret_path = base_dir / "client_secret.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing existing credentials...")
            creds.refresh(Request())
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(client_secret_path), SCOPES
                )
            except FileNotFoundError:
                print("\nERROR: 'client_secret.json' not found!")
                print("Please ensure your 'client_secret.json' file is in the 'calendar_agent/' directory.")
                print("You can download it from the Google Cloud Console (APIs & Services -> Credentials -> OAuth 2.0 Client IDs -> Download Client Configuration).")
                return None
            except Exception as e:
                print(f"\nAn error occurred while loading client secrets: {e}")
                return None

            flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"

            print("\n--- AUTOMATIC AUTHORIZATION ---")
            print("1. Your browser will open automatically with the authorization page.")
            print("2. Grant the requested permissions.")
            print("3. Copy the verification code displayed.")
            print("4. Paste the code here and press Enter.")
            print("----------------------------------")

            auth_url, _ = flow.authorization_url(prompt='consent')
            print(f"\nOpening authorization URL in your browser...")
            
            # Automatically open the authorization URL in the default browser
            try:
                webbrowser.open(auth_url)
                print("✅ Browser opened successfully!")
            except Exception as e:
                print(f"⚠️ Could not open browser automatically: {e}")
                print(f"Please manually copy and paste this URL: {auth_url}")
            
            print("\nWaiting for verification code...")
            code = input("Enter the verification code here: ").strip()
            if not code:
                print("No code entered. Authentication cancelled.")
                return None

            try:
                flow.fetch_token(code=code)
                creds = flow.credentials
            except Exception as e:
                print(f"Error exchanging code for tokens. Please try again: {e}")
                print("Ensure you copied the entire verification code correctly.")
                return None

        with token_path.open("w") as token:
            token.write(creds.to_json())
            print("\nCredentials saved to 'token.json'.")
    
    return creds

def google_calendar_list_events(creds, calendar_id="primary", time_min=None, time_max=None, max_results=10):
    """
    Lists events from a specified Google Calendar within a time range.
    This remains a synchronous function.
    """
    if not creds:
        print("Authentication failed. Cannot list events.")
        return []

    try:
        service = build("calendar", "v3", credentials=creds)
        print(f"\nFetching events from calendar: '{calendar_id}'...")

        if time_min is None:
            time_min = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30))
        if time_max is None:
            time_max = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365)

        time_min_utc = time_min.astimezone(datetime.UTC)
        time_max_utc = time_max.astimezone(datetime.UTC)

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min_utc.isoformat().replace("+00:00", "Z"),
                timeMax=time_max_utc.isoformat().replace("+00:00", "Z"),
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            print(f"No events found in calendar '{calendar_id}' between {time_min.strftime('%Y-%m-%d')} and {time_max.strftime('%Y-%m-%d')}.")
            return []

        print(f"Events found in '{calendar_id}':")
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            summary = event.get("summary", "No Title")
            print(f"- {start} to {end} | {summary}")
        return events
    except HttpError as error:
        print(f"\nAn API error occurred while listing events: {error}")
        return []
    except Exception as e:
        print(f"\nAn unexpected error occurred while listing events: {e}")
        return []

def google_calendar_create_event(creds, event_request: CalendarEventRequest):
    """
    Creates an event on a specified Google Calendar using a CalendarEventRequest.
    This remains a synchronous function.
    """
    if not creds:
        print("Authentication failed. Cannot create event.")
        return None

    if not event_request.summary or not event_request.start_time or not event_request.end_time:
        print("Summary, start_time, and end_time are required to create an event.")
        return None

    try:
        service = build("calendar", "v3", credentials=creds)
        
        # Parse the ISO format strings to datetime objects
        try:
            start_dt = datetime.datetime.fromisoformat(event_request.start_time)
            end_dt = datetime.datetime.fromisoformat(event_request.end_time)
        except ValueError as e:
            print(f"Invalid date format: {e}")
            return None

        start_utc = start_dt.astimezone(datetime.UTC)
        end_utc = end_dt.astimezone(datetime.UTC)

        event = {
            'summary': event_request.summary,
            'description': event_request.description,
            'start': {
                'dateTime': start_utc.isoformat().replace("+00:00", "Z"),
                'timeZone': event_request.time_zone,
            },
            'end': {
                'dateTime': end_utc.isoformat().replace("+00:00", "Z"),
                'timeZone': event_request.time_zone,
            },
        }
        
        if event_request.attendees:
            event['attendees'] = [{'email': email} for email in event_request.attendees]

        print(f"\nAttempting to create event: '{event_request.summary}' on calendar '{event_request.calendar_id}'...")
        created_event = service.events().insert(calendarId=event_request.calendar_id, body=event).execute()
        
        print(f"Event created: '{created_event.get('htmlLink')}'")
        return created_event
    except HttpError as error:
        print(f"\nAn API error occurred while creating event: {error}")
        return None
    except Exception as e:
        print(f"\nAn unexpected error occurred while creating event: {e}")
        return None

def google_calendar_get_availability(creds, calendar_ids, time_min=None, time_max=None, time_zone="UTC"):
    """
    Checks the free/busy status for specified calendars or attendees.
    This remains a synchronous function.
    """
    if not creds:
        print("Authentication failed. Cannot get availability.")
        return None

    if not calendar_ids:
        print("At least one calendar ID is required to get availability.")
        return None

    try:
        service = build("calendar", "v3", credentials=creds)

        if time_min is None:
            time_min = datetime.datetime.now(datetime.UTC)
        if time_max is None:
            time_max = time_min + datetime.timedelta(days=7)

        time_min_utc = time_min.astimezone(datetime.UTC)
        time_max_utc = time_max.astimezone(datetime.UTC)

        body = {
            "timeMin": time_min_utc.isoformat().replace("+00:00", "Z"),
            "timeMax": time_max_utc.isoformat().replace("+00:00", "Z"),
            "timeZone": time_zone,
            "items": [{"id": cal_id} for cal_id in calendar_ids],
        }

        print(f"\nChecking availability for calendars {calendar_ids} from {time_min.strftime('%Y-%m-%d %H:%M')} to {time_max.strftime('%Y-%m-%d %H:%M')}...")
        
        free_busy_response = service.freebusy().query(body=body).execute()
        
        calendars_availability = free_busy_response.get("calendars", {})
        
        if not calendars_availability:
            print("No availability information found for the specified calendars.")
            return None

        print("\n--- Availability Report ---")
        for cal_id, data in calendars_availability.items():
            print(f"Calendar: {cal_id}")
            busy_periods = data.get("busy", [])
            if busy_periods:
                print("   Busy Periods:")
                for busy_period in busy_periods:
                    start = busy_period['start']
                    end = busy_period['end']
                    print(f"     - From {start} to {end}")
            else:
                print("   No busy periods found in the specified range (appears free).")
        print("---------------------------")
        return calendars_availability
    except HttpError as error:
        print(f"\nAn API error occurred while getting availability: {error}")
        return None
    except Exception as e:
        print(f"\nAn unexpected error occurred while getting availability: {e}")
        return None


# --- Async Wrappers for synchronous Google API calls ---
async def async_authenticate_google_calendar():
    return await asyncio.to_thread(authenticate_google_calendar)

async def async_google_calendar_list_events(creds, calendar_id="primary", time_min=None, time_max=None, max_results=10):
    return await asyncio.to_thread(
        google_calendar_list_events, creds, calendar_id, time_min, time_max, max_results
    )

async def async_google_calendar_create_event(creds, event_request: CalendarEventRequest):
    return await asyncio.to_thread(
        google_calendar_create_event, creds, event_request
    )

async def async_google_calendar_get_availability(creds, calendar_ids, time_min=None, time_max=None, time_zone="UTC"):
    # calendar_ids for get_availability expects a list, so ensure it's a list here
    if isinstance(calendar_ids, str):
        calendar_ids = [calendar_ids]
    return await asyncio.to_thread(
        google_calendar_get_availability, creds, calendar_ids, time_min, time_max, time_zone
    )


# --- CREWAI TOOL DEFINITIONS ---
class ListCalendarEventsTool(BaseTool):
    name: str = "list_calendar_events"
    description: str = "Lists events from a specified Google Calendar within a time range (ISO 8601 format for dates). calendar_id can be 'primary' or an email address."
    
    def _run(self, calendar_id: str = "primary", time_min: Optional[str] = None, time_max: Optional[str] = None, max_results: int = 10) -> str:
        # Convert string dates back to datetime if provided
        dt_time_min = None
        dt_time_max = None
        try:
            if time_min:
                dt_time_min = datetime.datetime.fromisoformat(time_min.replace('Z', '+00:00'))
            if time_max:
                dt_time_max = datetime.datetime.fromisoformat(time_max.replace('Z', '+00:00'))
        except ValueError as e:
            return f"Error parsing dates: {e}. Please ensure dates are in ISO 8601 format."

        creds = authenticate_google_calendar()
        if not creds:
            return "Authentication failed. Cannot list events."

        events = google_calendar_list_events(creds, calendar_id, dt_time_min, dt_time_max, max_results)
        if events:
            formatted = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                summary = event.get("summary", "No Title")
                formatted.append(f"- {summary} (Starts: {start}, Ends: {end})")
            return f"Found {len(events)} events in calendar '{calendar_id}':\n" + "\n".join(formatted)
        else:
            return f"No events found in calendar '{calendar_id}' for the specified range."

    async def _arun(self, calendar_id: str = "primary", time_min: Optional[str] = None, time_max: Optional[str] = None, max_results: int = 10) -> str:
        # Convert string dates back to datetime if provided
        dt_time_min = None
        dt_time_max = None
        if time_min:
            dt_time_min = datetime.datetime.fromisoformat(time_min.replace('Z', '+00:00'))
        if time_max:
            dt_time_max = datetime.datetime.fromisoformat(time_max.replace('Z', '+00:00'))
        
        # Get credentials for this tool instance
        creds = await async_authenticate_google_calendar()
        if not creds:
            return "Authentication failed. Cannot list events."
        
        # Corrected: Call async_google_calendar_list_events
        events = await async_google_calendar_list_events(creds, calendar_id, dt_time_min, dt_time_max, max_results)
        
        if events:
            # Format events into a more readable string or JSON
            formatted_events = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                summary = event.get("summary", "No Title")
                formatted_events.append(f"- {summary} (Starts: {start}, Ends: {end})")
            return f"Found {len(events)} events in calendar '{calendar_id}':\n" + "\n".join(formatted_events)
        else:
            return f"No events found in calendar '{calendar_id}' for the specified range."

class CreateCalendarEventTool(BaseTool):
    name: str = "create_calendar_event"
    description: str = "Creates an event on a specified Google Calendar. Requires summary, start_time (ISO 8601), and end_time (ISO 8601). Optional: description, time_zone, attendees (comma-separated emails)."
    
    def _run(self, summary: str, description: str = "", start_time: Optional[str] = None, end_time: Optional[str] = None, time_zone: str = "UTC", attendees: Optional[str] = None) -> str:
        if not start_time or not end_time:
            return "Error: start_time and end_time are required to create an event (ISO 8601 format)."
        if not summary:
            return "Error: summary is required to create an event."

        try:
            start_dt = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except ValueError as e:
            return f"Error parsing dates: {e}. Please ensure dates are in ISO 8601 format."

        attendee_list = None
        if attendees:
            attendee_list = [{'email': email.strip()} for email in attendees.split(',')]

        creds = authenticate_google_calendar()
        if not creds:
            return "Authentication failed. Cannot create event."

        # Create CalendarEventRequest object
        event_request = CalendarEventRequest(
            summary=summary,
            description=description,
            start_time=start_time,
            end_time=end_time,
            time_zone=time_zone,
            attendees=[email['email'] for email in attendee_list] if attendee_list else None
        )
        
        created_event = google_calendar_create_event(creds, event_request)
        if created_event:
            return f"Event '{summary}' created successfully: {created_event.get('htmlLink')}"
        else:
            return f"Failed to create event '{summary}'. Check logs for details."

    async def _arun(self, summary: str, description: str = "", start_time: Optional[str] = None, end_time: Optional[str] = None, time_zone: str = "UTC", attendees: Optional[str] = None) -> str:
        if not start_time or not end_time:
            return "Error: start_time and end_time are required to create an event (ISO 8601 format)."
        if not summary:
            return "Error: summary is required to create an event."
        
        # Convert string dates to datetime
        try:
            start_dt = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except ValueError as e:
            return f"Error parsing dates: {e}. Please ensure dates are in ISO 8601 format."
        
        # Parse attendees if provided
        attendee_list = None
        if attendees:
            attendee_list = [{'email': email.strip()} for email in attendees.split(',')]
        
        # Get credentials for this tool instance
        creds = await async_authenticate_google_calendar()
        if not creds:
            return "Authentication failed. Cannot create event."
        
        # Create CalendarEventRequest object
        event_request = CalendarEventRequest(
            summary=summary,
            description=description,
            start_time=start_time,
            end_time=end_time,
            time_zone=time_zone,
            attendees=[email['email'] for email in attendee_list] if attendee_list else None
        )
        
        # Call the async wrapper
        created_event = await async_google_calendar_create_event(creds, event_request)
        
        if created_event:
            return f"Event '{summary}' created successfully: {created_event.get('htmlLink')}"
        else:
            return f"Failed to create event '{summary}'. Check logs for details."

class GetAvailabilityTool(BaseTool):
    name: str = "get_calendar_availability"
    description: str = "Checks the free/busy status for specified calendars and returns structured availability data. calendar_ids can be comma-separated emails or 'primary'. time_min (ISO 8601) and time_max (ISO 8601) define the range."
    
    def _run(self, calendar_ids: str = "primary", time_min: Optional[str] = None, time_max: Optional[str] = None, time_zone: str = "UTC") -> str:
        cal_ids = [cal.strip() for cal in calendar_ids.split(',')]

        dt_time_min = None
        dt_time_max = None
        try:
            if time_min:
                dt_time_min = datetime.datetime.fromisoformat(time_min.replace('Z', '+00:00'))
            if time_max:
                dt_time_max = datetime.datetime.fromisoformat(time_max.replace('Z', '+00:00'))
        except ValueError as e:
            return f"Error parsing dates: {e}. Please ensure dates are in ISO 8601 format."

        creds = authenticate_google_calendar()
        if not creds:
            return "Authentication failed. Cannot get availability."

        result = google_calendar_get_availability(creds, cal_ids, dt_time_min, dt_time_max, time_zone)
        if result:
            # Return structured data instead of text report
            return self._format_availability_as_json(result, dt_time_min, dt_time_max)
        else:
            return "Failed to get availability information. Check logs for details."

    def _format_availability_as_json(self, availability_data, time_min, time_max):
        """Format availability data as structured JSON for better processing."""
        try:
            # Calculate total time range
            total_days = (time_max - time_min).days if time_max and time_min else 30
            
            # Find free time slots (inverse of busy periods)
            free_slots = []
            
            # For simplicity, let's create weekly slots and mark busy ones
            current_date = time_min
            while current_date < time_max:
                # Check if this day is busy
                day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + datetime.timedelta(days=1)
                
                is_busy = False
                for cal_id, data in availability_data.items():
                    busy_periods = data.get("busy", [])
                    for busy_period in busy_periods:
                        busy_start = datetime.datetime.fromisoformat(busy_period['start'].replace('Z', '+00:00'))
                        busy_end = datetime.datetime.fromisoformat(busy_period['end'].replace('Z', '+00:00'))
                        
                        # Check if this day overlaps with any busy period
                        if (day_start < busy_end and day_end > busy_start):
                            is_busy = True
                            break
                    if is_busy:
                        break
                
                if not is_busy:
                    # This day is free - create a slot
                    slot_end = min(day_end, time_max)
                    duration = (slot_end - day_start).days
                    
                    # Count weekdays (excluding weekends)
                    weekdays_count = 0
                    temp_date = day_start
                    while temp_date < slot_end:
                        if temp_date.weekday() < 5:  # Monday = 0, Friday = 4
                            weekdays_count += 1
                        temp_date += datetime.timedelta(days=1)
                    
                    free_slots.append({
                        "start_date": day_start.strftime("%Y-%m-%d"),
                        "end_date": slot_end.strftime("%Y-%m-%d"),
                        "duration": duration,
                        "weekdays_pto_count": weekdays_count,
                        "notes": "Available for travel"
                    })
                
                current_date += datetime.timedelta(days=1)
            
            # Return structured data
            return {
                "available_slots": free_slots,
                "total_days_checked": total_days,
                "free_slots_found": len(free_slots),
                "time_range": {
                    "start": time_min.strftime("%Y-%m-%d") if time_min else None,
                    "end": time_max.strftime("%Y-%m-%d") if time_max else None
                }
            }
            
        except Exception as e:
            return f"Error formatting availability data: {e}"

    async def _arun(self, calendar_ids: str = "primary", time_min: Optional[str] = None, time_max: Optional[str] = None, time_zone: str = "UTC") -> str:
        # Parse calendar IDs
        cal_ids = [cal.strip() for cal in calendar_ids.split(',')]
        
        # Convert string dates to datetime if provided
        dt_time_min = None
        dt_time_max = None
        try:
            if time_min:
                dt_time_min = datetime.datetime.fromisoformat(time_min.replace('Z', '+00:00'))
            if time_max:
                dt_time_max = datetime.datetime.fromisoformat(time_max.replace('Z', '+00:00'))
        except ValueError as e:
            return f"Error parsing dates: {e}. Please ensure dates are in ISO 8601 format."
        
        # Get credentials for this tool instance
        creds = await async_authenticate_google_calendar()
        if not creds:
            return "Authentication failed. Cannot get availability."
        
        result = await async_google_calendar_get_availability(creds, cal_ids, dt_time_min, dt_time_max, time_zone)
        
        if result:
            # Return structured data instead of text report
            return self._format_availability_as_json(result, dt_time_min, dt_time_max)
        else:
            return "Failed to get availability information. Check logs for details."

# --- MAIN EXECUTION for testing purposes ---
if __name__ == "__main__":
    async def test_calendar_tools():
        print("\n--- Testing Calendar Tools ---")
        credentials = await async_authenticate_google_calendar()
        if not credentials:
            print("Test script cannot proceed without successful authentication.")
            return

        today = datetime.datetime.now(datetime.UTC)
        tomorrow = today + datetime.timedelta(days=1)
        next_week = today + datetime.timedelta(days=7)

        # Test GetAvailabilityTool
        print("\n--- Testing GetAvailabilityTool ---")
        availability_tool = GetAvailabilityTool()
        avail_result = await availability_tool._arun(
            calendar_ids="primary",
            time_min=today.isoformat().replace('+00:00', 'Z'),
            time_max=next_week.isoformat().replace('+00:00', 'Z'),
            time_zone="UTC"
        )
        print(avail_result)

        # Test ListCalendarEventsTool
        print("\n--- Testing ListCalendarEventsTool ---")
        list_events_tool = ListCalendarEventsTool()
        list_result = await list_events_tool._arun(
            calendar_id="primary",
            time_min=today.isoformat().replace('+00:00', 'Z'),
            time_max=next_week.isoformat().replace('+00:00', 'Z'),
            max_results=5
        )
        print(list_result)

        # Test CreateCalendarEventTool
        print("\n--- Testing CreateCalendarEventTool ---")
        create_event_tool = CreateCalendarEventTool()
        event_summary = "CrewAI Test Event"
        event_description = "Automatically created by CrewAI agent for testing async capabilities."
        create_result = await create_event_tool._arun(
            summary=event_summary,
            description=event_description,
            start_time=tomorrow.isoformat().replace('+00:00', 'Z'),
            end_time=(tomorrow + datetime.timedelta(hours=1)).isoformat().replace('+00:00', 'Z'),
            time_zone="UTC"
        )
        print(create_result)

    asyncio.run(test_calendar_tools())
