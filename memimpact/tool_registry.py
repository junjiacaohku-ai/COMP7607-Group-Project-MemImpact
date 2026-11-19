from tool_sandbox.tools.contact import search_contacts
from tool_sandbox.tools.messaging import send_message_with_phone_number
from tool_sandbox.tools.reminder import add_reminder, remove_reminder, search_reminder

TOOL_REGISTRY = {
    "search_contacts": search_contacts,
    "send_message_with_phone_number": send_message_with_phone_number,
    "add_reminder": add_reminder,
    "search_reminder": search_reminder,
    "remove_reminder": remove_reminder,
}
