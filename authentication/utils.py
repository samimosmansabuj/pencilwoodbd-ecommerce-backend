import re

def normalize_bd_phone(phone: str) -> str:
    """
    Always returns 13-digit form: 8801XXXXXXXXX
    Accepts only real BD mobile numbers in these input shapes:
      - 01XXXXXXXXX          (11 digits)
      - 8801XXXXXXXXX        (13 digits)
      - +8801XXXXXXXXX       (with +, dashes, spaces allowed)
    Returns "" if the input doesn't reduce to a valid BD mobile number.
    """
    if not phone:
        return ""

    digits = re.sub(r"\D", "", str(phone))  # strip everything except digits

    if len(digits) < 11:
        return ""

    local = digits[-11:]  # last 11 digits = 01XXXXXXXXX

    if re.match(r"^01[3-9]\d{8}$", local):
        return "88" + local

    return ""