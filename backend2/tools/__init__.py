"""
Tools Package - LangChain Tools
All agent tools are defined here with @tool decorator
"""
from .appointment_tools import (
    check_availability,
    create_appointment,
    cancel_appointment,
    suggest_alternative_times
)
from .customer_tools import (
    check_customer,
    get_customer_appointments,
    create_customer
)
from .info_tools import (
    list_services,
    list_experts,
    check_campaigns
)

# Export all tools
__all__ = [
    # Appointment tools
    "check_availability",
    "create_appointment",
    "cancel_appointment",
    "suggest_alternative_times",
    # Customer tools
    "check_customer",
    "get_customer_appointments",
    "create_customer",
    # Info tools
    "list_services",
    "list_experts",
    "check_campaigns",
]

# Tool list for LangGraph
ALL_TOOLS = [
    check_availability,
    create_appointment,
    cancel_appointment,
    suggest_alternative_times,
    check_customer,
    get_customer_appointments,
    create_customer,
    list_services,
    list_experts,
    check_campaigns,
]
