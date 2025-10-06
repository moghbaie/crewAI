# Travel Planning System - Modular Structure

This directory contains a refactored travel planning system that was originally a single large file (`agent_sequential.py`). The code has been distributed across multiple modules for better maintainability and organization.

## 🚀 Quick Start

### Prerequisites
- Python 3.13.4+
- Required API keys (see Setup section below)

### Installation
```bash
# Navigate to the orchestrator_agent directory
cd orchestrator_agent

# Install dependencies
pip install -r requirements.txt
```

### Setup API Keys
Create a `.env` file in the `orchestrator_agent` directory:
```bash
# Required API Keys
GOOGLE_API_KEY=your_google_api_key_here
SERPAPI_API_KEY=your_serpapi_key_here

# Optional - LangWatch for tracing and monitoring
LANGWATCH_API_KEY=your_langwatch_key_here
```

## 🖥️ Running the Application

### Option 1: Web Interface (Chainlit)
Run the interactive web application:

```bash
# Navigate to the orchestrator_agent directory
cd orchestrator_agent

# Start the web interface
chainlit run app.py
```

This will start a web server at `http://localhost:8000` where you can:
- Chat with the travel planning assistant
- Get interactive travel recommendations
- Select from multiple options
- Book trips directly in your calendar

### Option 2: Command Line Interface
Run the command-line version:

```bash
# Navigate to the orchestrator_agent directory
cd orchestrator_agent

# Interactive mode (prompts for input)
python agent_sequential.py

# Direct command with travel request (positional arguments)
python agent_sequential.py "I want to travel to Paris next month for 5 days"

# Using the --request option (optional)
python agent_sequential.py --request "Plan a trip to Tokyo in December"
```

### Option 3: Modular CLI
Use the new modular structure:

```bash
# Navigate to the orchestrator_agent directory
cd orchestrator_agent

# Interactive mode (prompts for input)
python main.py

# Direct command with travel request (positional arguments)
python main.py "I want to travel to London for 7 days in March"

# Using the --request option (optional)
python main.py --request "Plan a trip to Barcelona in April"
```

## 📁 File Structure

### Core Modules

- **`models.py`** - Contains all Pydantic data models used throughout the system
  - `TravelRequest`, `CalendarRequest`, `AvailableSlot`
  - `FlightRequest`, `HotelRequest`, `ItineraryRequest`
  - `FlightInfo`, `HotelInfo`, `AIResponse`

- **`config.py`** - Configuration and initialization logic
  - Environment variable loading
  - API key validation
  - LLM initialization with caching
  - Tool initialization
  - LangWatch setup

- **`utils.py`** - Utility functions
  - Date handling (`get_current_date()`)
  - Location detection (`get_current_location_async()`)

- **`agents.py`** - Agent definitions and task creation
  - `create_orchestrator_agent()`
  - `create_flight_search_agent()`
  - `create_calendar_agent()`
  - `create_orchestrator_task()`

- **`orchestrator.py`** - Main orchestration logic
  - `run_orchestrator()` - Core workflow coordination
  - Crew setup and execution
  - LangWatch tracing integration

- **`main.py`** - CLI entrypoint
  - Command-line interface
  - Application initialization

### Application Files

- **`app.py`** - Chainlit web application
  - Interactive web interface
  - Real-time chat with travel assistant
  - Visual travel option selection

- **`agent_sequential.py`** - Command-line application
  - Backward compatibility wrapper
  - CLI interface for travel planning
  - Can be used as a drop-in replacement

## 🔧 Configuration

### Required API Keys

1. **Google API Key** (for Gemini LLM)
   - Get from [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Used for AI-powered travel planning

2. **SerpAPI Key** (for search functionality)
   - Get from [SerpAPI](https://serpapi.com/)
   - Used for flight and hotel searches

### Optional API Keys

3. **LangWatch API Key** (for tracing)
   - Get from [LangWatch](https://langwatch.ai/)
   - Used for monitoring and debugging

### Google Calendar Integration

For calendar functionality, you'll also need:
- `client_secret.json` - Google Calendar API credentials
- `token.json` - Generated authentication token

## 🎯 Features

- **AI-Powered Travel Planning** - Uses CrewAI agents for intelligent trip planning
- **Calendar Integration** - Checks availability and books trips in Google Calendar
- **Flight & Hotel Search** - Finds the best deals using SerpAPI
- **Multiple Interfaces** - Web UI and command-line options
- **Modular Architecture** - Easy to maintain and extend

## 🔍 Troubleshooting

### Common Issues

1. **Missing API Keys Error**
   ```
   ValueError: Missing API keys! Add them to your .env file.
   ```
   **Solution:** Create a `.env` file with your API keys (see Setup section)

2. **Module Not Found Error**
   ```
   ModuleNotFoundError: No module named 'crewai'
   ```
   **Solution:** Install dependencies with `pip install -r requirements.txt`

3. **Google Calendar Authentication Error**
   ```
   Authentication failed.
   ```
   **Solution:** Ensure `client_secret.json` is present and properly configured

## 📝 Usage Examples

### Web Interface
```bash
# Navigate to the orchestrator_agent directory
cd orchestrator_agent

# Start the web app
chainlit run app.py

# Then in the browser:
# 1. Type: "I want to plan a trip to Paris for 5 days in March"
# 2. Select from the presented options
# 3. Confirm your booking
```

### Command Line
```bash
# Navigate to the orchestrator_agent directory
cd orchestrator_agent

# Interactive mode (prompts for input)
python agent_sequential.py
# Enter: "Plan a trip to London for 7 days"

# Direct command (positional arguments)
python agent_sequential.py "I want to travel to Tokyo next month for 10 days"

# Using --request option (optional)
python agent_sequential.py --request "Plan a trip to Rome in May"
```

## 🏗️ Benefits of This Structure

1. **Separation of Concerns** - Each module has a single responsibility
2. **Maintainability** - Easier to locate and modify specific functionality
3. **Testability** - Individual modules can be tested in isolation
4. **Reusability** - Components can be imported and used independently
5. **Scalability** - New features can be added to appropriate modules
6. **Multiple Interfaces** - Both web and CLI options available
