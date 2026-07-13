PROFILES = {
    "IN": {
        "required_form_fields": [
            "legal_name",
            "address.line1",
            "address.city",
            "address.state",
            "address.postal_code",
            "tax_id",
            "bank.account_number",
            "bank.ifsc",
            "bank.beneficiary_name",
            "contact.email",
        ],
        "required_documents": ["tax_certificate", "bank_proof"],
        "tax_id_kind": "GSTIN",
        "bank_code_kind": "IFSC",
    },
}

FIELD_LABELS = {
    "legal_name": "legal name",
    "address.line1": "address line 1",
    "address.city": "city",
    "address.state": "state",
    "address.postal_code": "postal code",
    "tax_id": "GSTIN",
    "bank.account_number": "bank account number",
    "bank.ifsc": "IFSC",
    "bank.beneficiary_name": "beneficiary name",
    "contact.email": "contact email",
    "tax_certificate": "GST registration certificate",
    "bank_proof": "bank proof (cancelled cheque / statement)",
}

# Aliases used by gstin_state_vs_address for fixture states only.
STATE_ALIASES = {
    "bengaluru": "karnataka",
    "bangalore": "karnataka",
    "mysore": "karnataka",
    "mysuru": "karnataka",
    "mumbai": "maharashtra",
    "pune": "maharashtra",
    "bombay": "maharashtra",
}
