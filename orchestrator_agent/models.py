"""
Pydantic models for travel planning system.
Contains all data structures used throughout the application.
"""

from typing import List, Optional
from pydantic import BaseModel


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
