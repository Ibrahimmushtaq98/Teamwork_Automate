# Teamwork_Automate
Im lazy to input any time entry in Teamwork, so this is a way to automate this

`teamwork_automate_script.py` fills in your Teamwork timesheet for every weekday from a start Monday up to today:

- **Regular days** get the entries listed in `time_entries_data.json`.
- **Ontario stat holidays** get a single 8h entry under **Labourly → Statutory Holiday**, with the holiday name as the description, instead of the regular entries.
- **Days that already have time logged are skipped**, so re-running it never double-posts.

## Setup (one time)

1. Install the dependencies (Python 3.9+):
   ```
   pip install requests python-dotenv tzdata
   ```
   `tzdata` is needed on Windows for the Toronto time zone.

2. Create a `.env` file next to the script (see `example.env`):
   ```
   TEAMWORK_API=<your Teamwork API key>
   TEAMWORK_BASEURL=https://<your-site>.teamwork.com
   ```
   `.env` is gitignored, so it never gets committed.

## Running it

Always preview first with `--dry-run`. It shows every entry it would post and which days it would skip, and it posts nothing.

```
python teamwork_automate_script.py --start 2026-11-16 --dry-run
```

If the preview looks right, run it for real:

```
python teamwork_automate_script.py --start 2026-11-16
```

| Option | What it does | Default |
|---|---|---|
| `--start YYYY-MM-DD` | First day to fill. Must be a Monday. | Monday of the current week |
| `--end YYYY-MM-DD` | Last day to fill (inclusive). | Today |
| `--dry-run` | Preview only, nothing is posted. | Off |

Running it with no options fills this week from Monday through today:

```
python teamwork_automate_script.py
```

Weekends are always skipped. Any day that already has time logged by you is skipped as a whole. If that day's total isn't 8h, the script prints a warning so you can fix it by hand in Teamwork.

## Changing your daily entries

Edit `time_entries_data.json`. No code changes needed.

```json
{
    "project_name": "Resonant Solutions",
    "timezone": "America/Toronto",
    "time_entries": [
        {
            "WEEKDAY": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
            "description": "Team Huddle",
            "task_list": "Admin (RS Core)",
            "task": "Meetings & Communications",
            "billable": false,
            "time_start": "09:00:00",
            "time_end": "09:30:00",
            "type": "REGULAR"
        }
    ],
    "stat_holiday": {
        "task_list": "Labourly",
        "task": "Statutory Holiday",
        "billable": false,
        "time_start": "09:00:00",
        "hours": 8,
        "move_weekend_holidays_to_next_weekday": true
    }
}
```

- **Times are local Toronto time.** The script converts them to UTC for each date, so daylight saving time is handled automatically.
- **Duration** is `time_end - time_start`.
- **`WEEKDAY`** controls which days an entry applies to, so you can have an entry only on certain days.
- **`task_list` / `task`** must match the names in Teamwork exactly. The script looks up their IDs and stops before posting anything if one isn't found.

## Stat holidays

Dates are calculated automatically for every year, so there's nothing to update. These are the nine [Ontario public holidays](https://www.ontario.ca/document/your-guide-employment-standards-act-0/public-holidays):

| Holiday | Rule |
|---|---|
| New Year's Day | Jan 1 |
| Family Day | 3rd Monday of February |
| Good Friday | 2 days before Easter |
| Victoria Day | Monday before May 25 |
| Canada Day | Jul 1 |
| Labour Day | 1st Monday of September |
| Thanksgiving Day | 2nd Monday of October |
| Christmas Day | Dec 25 |
| Boxing Day | Dec 26 |

If a holiday falls on a weekend, it moves to the next free weekday and is labelled "(observed)". For example, Boxing Day 2026 is on Saturday, so it's logged on Monday Dec 28. Set `move_weekend_holidays_to_next_weekday` to `false` to turn this off.

Civic Holiday (August) and Remembrance Day are **not** Ontario stat holidays, so they're logged as regular days.

## Other files

- `teamwork_client.py`: small wrapper around the Teamwork v3 API.
- `teamwork_notebook.ipynb`: the original notebook for testing the API. The script replaces the weekly "set the Monday and press play" step.
