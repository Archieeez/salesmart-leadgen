"""
Data source layer.

This is the ONE place in the whole project that knows where company data
comes from. Right now it reads from a local CSV (our free mock dataset).

Later, when there's budget for Google Places API (or another provider),
you swap the INSIDE of get_company_data() only. Nothing in main.py or
store.py needs to change, because they only ever call this function and
never care how the data was actually fetched.
"""

import csv
import os

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "companies_seed.csv")


def get_company_data(company_name: str) -> dict | None:
    """
    Look up a company by name.

    Returns a dict with keys: company_name, address, phone, website
    Returns None if not found.

    TODO (later, once you have API budget/approval):
    Replace the CSV lookup below with a real Google Places API call.
    Keep the same return shape (same dict keys) so nothing downstream breaks.
    """
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["company_name"].strip().lower() == company_name.strip().lower():
                return {
                    "company_name": row["company_name"],
                    "address": row["address"],
                    "phone": row["phone"],
                    "website": row["website"],
                }
    return None


def get_all_companies() -> list[dict]:
    """Return every company currently in the seed CSV."""
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            {
                "company_name": row["company_name"],
                "address": row["address"],
                "phone": row["phone"],
                "website": row["website"],
            }
            for row in reader
        ]


if __name__ == "__main__":
    # Quick manual test: python src/data_source.py
    result = get_company_data("Tokopedia")
    print(result)
