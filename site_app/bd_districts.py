
BD_DISTRICTS = [
    "Bagerhat", "Bandarban", "Barguna", "Barishal", "Bhola",
    "Bogura", "Brahmanbaria", "Chandpur", "Chattogram", "Chuadanga",
    "Cox's Bazar", "Cumilla", "Dhaka", "Dinajpur", "Faridpur",
    "Feni", "Gaibandha", "Gazipur", "Gopalganj", "Habiganj",
    "Jamalpur", "Jashore", "Jhalokati", "Jhenaidah", "Joypurhat",
    "Khagrachhari", "Khulna", "Kishoreganj", "Kurigram", "Kushtia",
    "Lakshmipur", "Lalmonirhat", "Madaripur", "Magura", "Manikganj",
    "Meherpur", "Moulvibazar", "Munshiganj", "Mymensingh", "Naogaon",
    "Narail", "Narayanganj", "Narsingdi", "Natore", "Nawabganj",
    "Netrokona", "Nilphamari", "Noakhali", "Pabna", "Panchagarh",
    "Patuakhali", "Pirojpur", "Rajbari", "Rajshahi", "Rangamati",
    "Rangpur", "Satkhira", "Shariatpur", "Sherpur", "Sirajganj",
    "Sunamganj", "Sylhet", "Tangail", "Thakurgaon",
]

BD_DISTRICT_CHOICES = [(d, d) for d in BD_DISTRICTS]

_DISTRICT_LOOKUP = {d.lower(): d for d in BD_DISTRICTS}


def normalize_district(value):
    """Return the canonical BD_DISTRICTS spelling for `value`, or the
    original (stripped) value if it doesn't match anything known — we
    never want to silently drop a district just because it's unrecognized."""
    if not value:
        return value
    value = str(value).strip()
    return _DISTRICT_LOOKUP.get(value.lower(), value)


ALL_DISTRICTS_KEY = "all"

SYSTEM_DEFAULT_DELIVERY_CHARGE = 100