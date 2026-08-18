"""
Entry point. Run this with: python src/main.py

What it does, in order:
1. Make sure the database exists.
2. Pull every company from the current data source (CSV mock for now).
3. Save each one into the database.
4. Print out what's in the database, so you can see it actually worked.

This is intentionally the whole pipeline in ~15 lines. Resist the urge
to add config files, CLI arguments, or logging frameworks right now —
add those only when this simple version stops being enough.
"""

from data_source import get_all_companies
from store import init_db, save_lead, get_all_leads


def run_pipeline():
    init_db()

    companies = get_all_companies()
    print(f"Found {len(companies)} companies in data source.")

    for company in companies:
        save_lead(company)
        print(f"  saved: {company['company_name']}")

    print("\n--- Current leads in database ---")
    for lead in get_all_leads():
        print(lead)


if __name__ == "__main__":
    run_pipeline()
