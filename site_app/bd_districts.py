# site_app/bd_districts.py
"""
Static list of Bangladesh's 64 districts.
Kept as plain names (matching the names returned by the frontend's
`https://bdapi.vercel.app/api/v.1/district` API) so that the district
string saved on `Address.district` (order/models.py) matches exactly
the keys used in delivery-charge JSON configs.

If bdapi ever renames a district, update it here AND in any existing
area_and_charge JSON that used the old name (a small data-migration).
"""

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

# Choice tuples, in case any ModelForm/ChoiceField wants them
BD_DISTRICT_CHOICES = [(d, d) for d in BD_DISTRICTS]

# Sentinel key used inside area_and_charge JSON to mean
# "this charge applies to every district not explicitly listed"
ALL_DISTRICTS_KEY = "all"

# Absolute last-resort charge if nothing else resolves (Taka)
SYSTEM_DEFAULT_DELIVERY_CHARGE = 100