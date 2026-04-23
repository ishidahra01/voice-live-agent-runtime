"""Phase transition rules."""

# (current_phase, tool_name) -> next_phase
TRANSITIONS = {
    ("triage", "start_identity_verification"): "identity",
    ("triage", "escalate_to_human"): "escalation",
    ("identity", "verify_customer"): "business",  # Only if verified=True
    ("identity", "back_to_triage"): "triage",
    ("identity", "escalate_to_human"): "escalation",
    ("business", "escalate_to_human"): "escalation",
}

# Tools that terminate the session
TERMINAL_TOOLS = {"end_call", "create_escalation"}
