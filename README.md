# SaleSmart Lead Gen — v1 (Prototype)

## Scope (v1)

Fields collected per lead:
- Company name
- Company main address
- Company main phone number (business line, not personal direct-dial)
- Website
- (Planned, not yet built) AI-generated fit score + reasoning

**Explicitly out of scope for v1:** personal phone numbers, personal
emails, or any contact info tied to a specific individual. See notes
below on why.

## Data source (current)

`data/companies_seed.csv` — a small hand-verified set of real Indonesian
companies, used as a stand-in for a real data provider while there's no
API budget. All numbers/addresses cross-checked against each company's
own official contact page where possible.

This is temporary. The code is structured so this can be swapped for a
real source (Google Places API, business registry, etc.) later by
editing only `src/data_source.py` — nothing else in the project needs
to change.

## Why no personal contact info

1. Indonesia's UU PDP (Personal Data Protection Law) has been fully
   enforceable since October 2024, with real penalties for processing
   personal data without a lawful basis. A company's main switchboard
   number is business information; an individual's personal cell/email
   is personal data and requires a much higher compliance bar.
2. There is currently no budget for a data provider (Clearbit, PDL,
   ZoomInfo, etc.) that could legally source that tier of data.
3. An LLM cannot look up real personal contact info — asking it to
   would produce hallucinated (fake) numbers/emails, which is worse
   than having none.

If SaleSmart wants personal-level contact data later, that's a
buy-a-data-provider decision for leadership, not something to build
around scraping.

## How to run

```bash
cd src
python main.py
```

This will create `data/leads.db` (SQLite) and load the seed companies
into it.

## Project structure

```
salesmart-leadgen/
├── README.md
├── data/
│   └── companies_seed.csv   <- mock data source, expand this yourself
├── src/
│   ├── data_source.py       <- swap this out for a real API later
│   ├── store.py              <- SQLite storage
│   └── main.py                <- runs the pipeline end to end
```

## Next steps

- [ ] Get manager sign-off on this scope
- [ ] Expand `companies_seed.csv` to ~15-20 companies (do this by hand —
      it's worth feeling how slow/inconsistent manual research is,
      that's the exact problem an eventual real API solves)
- [ ] Add email discovery (pattern-guessing + verification)
- [ ] Add AI scoring layer once there's real data to score
