"""
nav_map.py

A structured list of Trucheck portal pages/features, so the chatbot can
answer "how do I..." navigation questions by pointing to the exact screen -
not just quoting a paragraph from the FAQ.

*** EDIT THIS with Trucheck's real pages/paths before going live. ***
The placeholders below are guesses based on the FAQ content - replace the
"path" values with the actual routes/menu locations in your portal, and add
any pages not covered here.
"""

NAV_MAP = [
    {
        "name": "Create TruCheck",
        "path": "TruCheck home page > Create TruCheck button",
        "description": "Start a new verification request for a candidate "
        "(name, email, opportunity title, location of employment).",
    },
    {
        "name": "Dashboard",
        "path": "TruCheck home page",
        "description": "Shows all candidates and their current stage: "
        "Link Sent, Pending, Ready for Adjudication, Completed.",
    },
    {
        "name": "View Consent PDF",
        "path": "Dashboard > click a candidate row > View Consent PDF",
        "description": "Check a candidate's progress before they've finished - "
        "shows what they've completed and entered so far.",
    },
    {
        "name": "Ready for Adjudication queue",
        "path": "Dashboard > filter by 'Ready for Adjudication'",
        "description": "Records where QA review is done and a recruiter "
        "decision (Clear / Review Required) is needed.",
    },
    {
        "name": "VerifiedID Client Portal login",
        "path": "Portal link from the 'access provided' email",
        "description": "First-time login using the emailed username and "
        "temporary password, then set a new password.",
    },
]


def format_nav_map_for_prompt() -> str:
    """Render the nav map as plain text to inject into the system prompt."""
    lines = []
    for item in NAV_MAP:
        lines.append(f"- {item['name']} ({item['path']}): {item['description']}")
    return "\n".join(lines)
