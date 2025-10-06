"""
Chainlit web application for travel planning system.
Uses the modular structure from the refactored agent_sequential.py.
"""

import json
import sys
import logging
import chainlit as cl
from typing import List
from orchestrator import run_orchestrator
from config import setup_langwatch

# Initialize logger
logger = logging.getLogger(__name__)

# Global variable to store travel options
travel_options = []


@cl.on_chat_start
async def on_chat_start():
    """Initialize the chat session."""
    await cl.Message(content="Hello! I'm your personal travel planning assistant. How can I help you plan your next trip?").send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming messages from users."""
    user_travel_request = message.content

    if user_travel_request.strip().lower() == "exit":
        await cl.Message(content="Goodbye! Safe travels! ✈️").send()
        sys.exit(0)

    # Check if this is a user selection (1, 2, 3) or a new travel request
    if user_travel_request.strip() in ['1', '2', '3']:
        # This is a user selection - handle the booking
        await handle_user_selection(user_travel_request)
        return

    # This is a new travel request - start the planning process
    await cl.Message(content=f"🚀 Starting travel planning for: **{user_travel_request}**").send()

    try:
        # Run the travel planning orchestrator
        await cl.Message(content="🔍 Analyzing your request and checking calendar availability...").send()
        
        # Use the modular orchestrator function
        result = await run_orchestrator(user_travel_request)
        
        if result:
            await cl.Message(content=f"✅ Travel planning completed! Here's your result:\n\n{result}").send()
        else:
            await cl.Message(content="⚠️ No travel options were generated. Please try a different request.").send()

    except Exception as e:
        logger.error(f"Error during trip planning: {e}", exc_info=True)
        await cl.Message(content=f"❌ An error occurred during trip planning: {str(e)}").send()


async def handle_user_selection(selection: str):
    """Handle user's selection and proceed with booking."""
    await cl.Message(content=f"✅ You selected option {selection}. Processing your booking...").send()
    
    try:
        # For now, just confirm the selection
        # In a full implementation, this would integrate with the calendar booking
        await cl.Message(
            content=f"**🎉 Booking confirmed for option {selection}!**\n\n"
                    f"Your trip has been selected. In a full implementation, this would be added to your Google Calendar.\n\n"
                    f"**Selected Option:** {selection}\n"
                    f"**Status:** Confirmed ✅"
        ).send()
            
    except Exception as e:
        logger.error(f"Error during booking: {e}")
        await cl.Message(content=f"❌ An error occurred during booking: {str(e)}").send()


# Initialize the application
if __name__ == "__main__":
    # Setup LangWatch if available
    setup_langwatch()
    
    # This will be handled by Chainlit when running with: chainlit run app.py
    print("🔗 Chainlit mode activated - travel planning system ready for web interface")
    print("📝 To run: chainlit run app.py")
else:
    # This code runs when imported by Chainlit
    setup_langwatch()
    print("🔗 Chainlit mode activated - travel planning system ready for web interface")
