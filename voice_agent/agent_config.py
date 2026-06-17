from datetime import date
from config import VOICE_MODEL, LLM_MODEL
from deepgram.agent.v1 import (
    AgentV1Settings,
    AgentV1SettingsAudio,
    AgentV1SettingsAudioInput,
    AgentV1SettingsAudioOutput,
    AgentV1SettingsAgent,
    AgentV1SettingsAgentListen,
    AgentV1SettingsAgentListenProvider_V2,
)
from deepgram.types.think_settings_v1 import ThinkSettingsV1
from deepgram.types.think_settings_v1provider import ThinkSettingsV1Provider_OpenAi
from deepgram.types.think_settings_v1functions_item import ThinkSettingsV1FunctionsItem
from deepgram.types.speak_settings_v1 import SpeakSettingsV1
from deepgram.types.speak_settings_v1provider import SpeakSettingsV1Provider_Deepgram

_TODAY = date.today()
_TODAY_STR = _TODAY.strftime("%A, %B %d, %Y")

SYSTEM_PROMPT = f"""You are Alex, a friendly and professional voice receptionist at Optimist Computers, a top electronics retailer and wholesaler in Nehru Place, New Delhi. You are answering an incoming customer call.

TODAY'S DATE: {_TODAY_STR}

VOICE FORMATTING RULES:
You are a VOICE agent. Your responses are spoken aloud via text-to-speech.
- Use only plain conversational English
- NO markdown, emojis, asterisks, brackets, or special formatting
- Keep responses brief: 1 to 2 sentences per turn
- Never announce function calls (do not say "let me search that" or "running search")
- Speak numbers naturally (say "twenty one thousand rupees" or "forty two thousand rupees")

YOUR RESPONSIBILITIES:
1. Greet callers warmly and identify their needs
2. Assist with used and refurbished laptop inquiries:
   - Check stock availability, laptop specs, and pricing
   - Check component availability (CPUs, RAM, monitors, motherboards)
3. Manage showroom visit reservations:
   - Book showroom visits for customers wanting to inspect or buy laptops
   - Check existing reservations
   - Cancel reservations (confirm before doing so)
4. Provide store information (timings, location, contact, warranties)
5. End calls gracefully

STORE INFORMATION:
- Name: Optimist Computers
- Location: Shop Ground Floor Number 5, Shakuntala Building, Building Number 59, Nehru Place, New Delhi, Pin Code 110019
- Hours: Monday through Saturday, 11 AM to 8 PM. Closed on Sundays.
- Offerings: Refurbished laptops, used laptops (Dell, HP, Lenovo, Asus, Acer), open-box Apple MacBooks, computer parts (CPUs, RAM, motherboards, monitors).
- Warranty: 1 month testing and replacement warranty on refurbished/used laptops. Remaining brand warranty on open-box items.
- Contact: Primary call numbers 7678583898 and 9643551125. WhatsApp/Catalog catalog is +91 93555 01543.

FUNCTION CALL RULES:
You can invoke the following tools based on conversation context:

For search_laptop_inventory:
- Call this whenever the customer asks about stock availability, specific brands, prices, or specs
- If they ask generally, call it with no parameters to get featured items
- No confirmation needed before calling this tool

For reserve_laptop_or_visit:
- Call this to reserve a laptop or book a showroom visit
- FIRST confirm details: "I can reserve that MacBook Air M1 for you on Monday January 6th at 2 PM. Shall I book that showroom visit for you?"
- WAIT for the customer to confirm
- THEN call the function. You'll need their name, phone number, and the laptop model

For check_reservation:
- Call this when a customer asks to look up their visit reservation. Provide name or phone number

For cancel_reservation:
- FIRST confirm: "I can cancel your showroom visit on [date] for the [model]. Are you sure?"
- WAIT for confirmation, then call it

For end_call:
- Call this after concluding the call and saying goodbye. Goodbye must be spoken first

CONVERSATION STYLE:
- Be welcoming, polite, and professional
- Ask one question at a time
- Speak in clear English. If the customer uses Hindi words like "mil jayega" or "kitne ka hai", answer politely in simple English using Indian pricing terms (e.g. Rupees)
"""

GREETING = "Thank you for calling Optimist Computers. My name is Alex, how can I help you today?"

FUNCTIONS = [
    ThinkSettingsV1FunctionsItem(
        name="search_laptop_inventory",
        description="""Search the current stock of refurbished, used, and open-box laptops.
Call this when a customer asks about laptop models, brands, specifications, prices, or generally what's in stock.
This is a read-only lookup — no confirmation is needed before calling.""",
        parameters={
            "type": "object",
            "properties": {
                "brand": {
                    "type": "string",
                    "description": "Laptop brand to filter by (e.g., 'Apple', 'Dell', 'Lenovo', 'HP')."
                },
                "max_price": {
                    "type": "integer",
                    "description": "Maximum price in Indian Rupees (INR) (e.g., 30000)."
                },
                "query": {
                    "type": "string",
                    "description": "General search query for specifications or keywords (e.g., 'i5', '16GB RAM', 'gaming')."
                }
            },
            "required": []
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="reserve_laptop_or_visit",
        description="""Reserve a laptop for 24 hours and schedule a showroom visit.
IMPORTANT: Before calling this, you MUST:
1. Confirm the laptop model, visit date, and visit time with the caller.
2. Collect the customer's name and phone number.
3. Wait for the customer to explicitly say yes or confirm.
Only call this tool after explicit confirmation.""",
        parameters={
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Full name of the customer"
                },
                "customer_phone": {
                    "type": "string",
                    "description": "Contact phone number of the customer"
                },
                "laptop_model": {
                    "type": "string",
                    "description": "Model of the laptop being reserved (e.g. 'MacBook Air M1' or 'ThinkPad T480')"
                },
                "visit_date": {
                    "type": "string",
                    "description": "Visit date in YYYY-MM-DD format. E.g. '2026-06-25'"
                },
                "visit_time": {
                    "type": "string",
                    "description": "Visit time in 24-hour format HH:MM. E.g. '14:30'"
                }
            },
            "required": ["customer_name", "customer_phone", "laptop_model", "visit_date", "visit_time"]
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="check_reservation",
        description="""Look up a customer's active showroom visit reservation.
Call this when a customer asks about their reservation. No confirmation is needed before calling.""",
        parameters={
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Name of the customer to search for"
                },
                "customer_phone": {
                    "type": "string",
                    "description": "Phone number of the customer to search for"
                }
            },
            "required": []
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="cancel_reservation",
        description="""Cancel an active showroom visit reservation.
IMPORTANT: Before calling this, you MUST:
1. Look up the reservation using check_reservation
2. Confirm with the patient: 'I can cancel your showroom visit reservation [reservation_id]. Are you sure?'
3. WAIT for the patient to confirm they want to cancel.""",
        parameters={
            "type": "object",
            "properties": {
                "reservation_id": {
                    "type": "string",
                    "description": "The reservation ID to cancel"
                }
            },
            "required": ["reservation_id"]
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="end_call",
        description="""Hang up the call. Call this only when the caller says goodbye, the conversation is naturally finished, or no further action is needed. Say goodbye FIRST.""",
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why the call is ending",
                    "enum": ["visit_reserved", "customer_goodbye", "general_inquiry_resolved"]
                }
            },
            "required": ["reason"]
        }
    ),
]


def get_agent_config() -> AgentV1Settings:
    """Build the settings payload for Deepgram Voice Agent API."""
    return AgentV1Settings(
        type="Settings",
        audio=AgentV1SettingsAudio(
            input=AgentV1SettingsAudioInput(
                encoding="mulaw",
                sample_rate=8000,
            ),
            output=AgentV1SettingsAudioOutput(
                encoding="mulaw",
                sample_rate=8000,
                container="none",
            ),
        ),
        agent=AgentV1SettingsAgent(
            listen=AgentV1SettingsAgentListen(
                provider=AgentV1SettingsAgentListenProvider_V2(
                    version="v2",
                    type="deepgram",
                    model="flux-general-en",
                ),
            ),
            think=ThinkSettingsV1(
                provider=ThinkSettingsV1Provider_OpenAi(
                    type="open_ai",
                    model=LLM_MODEL,
                ),
                prompt=SYSTEM_PROMPT,
                functions=FUNCTIONS,
            ),
            speak=SpeakSettingsV1(
                provider=SpeakSettingsV1Provider_Deepgram(
                    type="deepgram",
                    model=VOICE_MODEL,
                ),
            ),
            greeting=GREETING,
        ),
    )
