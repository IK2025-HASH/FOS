"""
seed_dev_data.py
Run once to pre-populate test companies. Safe to re-run — skips if already exists.

Usage:  python seed_dev_data.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.database import db
from core.models import EntityModel

db.open("devpass")

ADDRESS = dict(
    line1    = "111 Hawlands",
    line2    = "",
    town     = "Rugby",
    county   = "Warwickshire",
    postcode = "CV21 1JR",
)

COMPANIES = [
    dict(
        legal_name          = "Network Logic Limited",
        trading_name        = None,
        company_number      = "12345678",
        entity_type         = "Limited Company",
        fy_start            = "April",
        fy_end              = "March",
        reg_address         = ADDRESS,
        trading_address     = None,
        vat_registered      = True,
        vat_number          = "GB123456789",
        vat_scheme          = "Flat Rate",
        flat_rate_pct       = 14.0,
        quarter_start_month = 4,
        banks               = [
            {"account_name": "Barclays", "sort_code": "", "account_number": ""},
            {"account_name": "Starling", "sort_code": "", "account_number": ""},
        ],
        approver_name       = "Ilyas Kadri",
        approver_role       = "Director",
        approver_email      = "ilyas.kadri@gmail.com",
    ),
    dict(
        legal_name          = "Fusion Cafe Ltd",
        trading_name        = "Fusion Cafe",
        company_number      = "87654321",
        entity_type         = "Limited Company",
        fy_start            = "April",
        fy_end              = "March",
        reg_address         = ADDRESS,
        trading_address     = None,
        vat_registered      = False,
        vat_number          = "",
        vat_scheme          = "Standard Accrual",
        flat_rate_pct       = None,
        quarter_start_month = 4,
        banks               = [
            {"account_name": "Starling", "sort_code": "", "account_number": ""},
        ],
        approver_name       = "Ilyas Kadri",
        approver_role       = "Director",
        approver_email      = "ilyas.kadri@gmail.com",
    ),
]

existing = {e["legal_name"] for e in EntityModel.list_all()}

for co in COMPANIES:
    if co["legal_name"] in existing:
        print(f"  SKIP  {co['legal_name']} (already exists)")
    else:
        entity_id = EntityModel.create(**co)
        print(f"  OK    {co['legal_name']} created ({entity_id[:8]}...)")

db.close()
print("\nDone. Run: python app.py")
