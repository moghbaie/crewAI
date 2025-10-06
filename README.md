# CrewAI Agents

This repository contains two specialized AI agents built with CrewAI framework for different tasks: calendar management and flight search.

## Prerequisites

- Python 3.13.4
- Virtual environment (recommended)
- Required API keys (see Environment Setup below)

## Environment Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd crewai
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv .venv
   
   # On Windows:
   .venv\Scripts\activate
   
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   uv pip install -r requirements.txt
   ```

4. **Set up environment variables and credentials:**
   
   **Create a `.env` file in the root directory with your API keys:**
   ```env
   GOOGLE_API_KEY=your_google_api_key_here
   SERPAPI_API_KEY=your_serpapi_key_here
   ```
   
   **For Calendar Agent (Google Calendar API):**
   - Download your `client_secret.json` from Google Cloud Console
   - Place it in the `calendar_agent/` directory
   - The `token.json` will be generated automatically on first run

## Agents

### 1. Calendar Agent (`calendar_agent/`)

**Purpose:** Manages Google Calendar operations including creating, updating, and retrieving calendar events.

**Features:**
- Create new calendar events
- Update existing events
- Retrieve calendar information
- Google Calendar API integration

**How to run:**
```bash
cd calendar_agent
python agent.py
```

**Requirements:**
- Google Calendar API credentials (`client_secret.json`)
- Valid Google API key
- Proper authentication setup

### 2. Flight Search Agent (`flight_search_agent/`)

**Purpose:** Searches for available flights using web search capabilities and provides structured flight information.

**Features:**
- Search for flights between destinations
- Retrieve flight details including:
  - Date of travel
  - Price information
  - Airline names (when available)
  - Origin and destination airports
  - Number of stops
  - Cabin class options
  - Flight numbers (when available)
- Web search integration via SerpAPI
- **Note**: Booking links are simulated for demonstration purposes

**How to run:**
```bash
cd flight_search_agent
python agent.py
```

**Requirements:**
- SerpAPI key for web search functionality
- Google Gemini API key for LLM processing

### 3. Orchestrator Agent (`orchestrator_agent/`)

**Purpose:** Coordinates between Calendar and Flight Search agents to create comprehensive travel plans.

**Features:**
- Automatically detects current date and location
- Finds available travel windows considering PTO constraints
- Coordinates calendar availability checks
- Searches for flights and accommodations
- Ranks travel options by cost and PTO efficiency
- Books final selected trip in Google Calendar

**How to run:**
```bash
# Basic usage (defaults to Miami, 4 nights, $1,000 budget, 3 PTO days)
python orchestrator_agent/agent.py

# Custom destination and parameters
python orchestrator_agent/agent.py --destination Paris --nights 7 --budget '$2,500' --max-pto 5

# Short form options
python orchestrator_agent/agent.py -d Tokyo -n 5 -b '$3,000' -p 4 -m 6
```

**Command Line Options:**
- `--destination, -d`: Destination city (default: Miami)
- `--nights, -n`: Number of nights for the trip (default: 4)
- `--budget, -b`: Total budget for flights and accommodations (default: $1,000)
- `--max-pto, -p`: Maximum PTO days to use (default: 3)
- `--months-ahead, -m`: Months ahead to search for travel (default: 3)

**Requirements:**
- All Calendar Agent requirements
- All Flight Search Agent requirements
- Internet connection for location detection

## Auto-Detection Features

The Orchestrator Agent automatically detects:
- **Current Date**: Automatically uses today's date as the starting point
- **Current Location**: Uses IP geolocation to determine your city, region, and country
- **Available Travel Windows**: Calculates optimal travel dates considering PTO constraints and weekends

## Usage Examples

### Calendar Agent
The calendar agent can be used to:
- Schedule meetings and events
- Check calendar availability
- Manage recurring appointments
- Integrate with other scheduling systems

### Flight Search Agent
The flight search agent can be used to:
- Find flights between specific cities
- Compare prices across different airlines
- Check flight availability for specific dates
- Get direct booking links for flights

### Orchestrator Agent
The orchestrator agent can be used to:
- Plan complete trips with automatic date and location detection
- Find travel windows that minimize PTO usage
- Get ranked travel options based on cost and efficiency
- Automatically book selected trips in Google Calendar

## Troubleshooting

1. **API Key Issues:**
   - Ensure all required API keys are set in your `.env` file
   - Verify API key permissions and quotas

2. **Dependencies:**
   - Make sure all packages are installed: `uv pip install -r requirements.txt`
   - Check Python version compatibility

3. **Authentication:**
   - For calendar agent, ensure `client_secret.json` is properly configured
   - Run authentication flow if needed

4. **Flight Search Limitations:**
   - Flight search agent provides simulated data for demonstration
   - Real airline booking requires integration with airline APIs (e.g., Amadeus, Sabre)
   - Booking links are not functional and are for demonstration only

## Contributing

Feel free to submit issues and enhancement requests!

## License

[Add your license information here]

