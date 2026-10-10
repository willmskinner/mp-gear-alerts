# Mountain Project gear alerts

Checks the Mountain Project **For Sale / For Free / Want To Buy** forum every hour
and emails you (via Resend) when a new post matches one of your watches.

## Changing what you watch for

Edit [`config.yaml`](config.yaml), directly on GitHub if you like (pencil icon → commit).
The next hourly run picks it up. The keyword rules are explained at the top of that file.

## What triggers an alert

Each run looks at every topic with activity since the last run:

- **New listing**: a new topic whose title or first post matches.
- **Updated/bumped listing**: an older topic got a new reply and its title matches
  (catches sellers who edit titles like "ADDED: …"). Each listing alerts once per watch.
- **Reply**: a new reply whose text matches, e.g. in the "Free Gear" sticky thread.
  Replies in a listing you were already alerted to are skipped.

Topics whose title matches `exclude_titles` (WTB etc.) are skipped.

## How it works

- `state.json` stores the newest message ID seen and which topics already alerted.
  The workflow commits it back after each run.
- The first run just records a baseline and sends nothing.
- After 3 failed runs in a row (e.g. Mountain Project changed its page layout)
  you get one "scanner failing" email, and another when it recovers.

## Local use

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in values
.venv/bin/python run.py --dry-run      # print what would be emailed
.venv/bin/python run.py --test-email   # check email delivery
```

## Setup (GitHub)

- Secret `RESEND_API_KEY`
- Variables `FROM_EMAIL`, `NOTIFY_EMAIL`
