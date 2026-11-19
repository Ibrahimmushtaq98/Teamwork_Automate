"""
Fill in Teamwork time entries for every weekday from a start Monday up to today.

- Regular days use the entries in time_entries_data.json ("time_entries").
- Ontario statutory holidays get one 8h entry ("stat_holiday") with the holiday
  name as the description, instead of the regular entries.
- Days that already have time logged by you are skipped, so re-running is safe.

Usage:
    python teamwork_automate_script.py                      # this week's Monday -> today
    python teamwork_automate_script.py --start 2026-11-16   # given Monday -> today
    python teamwork_automate_script.py --start 2026-11-16 --dry-run
    python teamwork_automate_script.py --start 2026-11-16 --end 2026-11-20
"""
import argparse
import datetime
import json
import os
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import teamwork_client

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TIME_ENTRIES_FILE = os.path.join(SCRIPT_DIR, "time_entries_data.json")
WEEKDAY_NAMES = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
FULL_DAY_MINUTES = 8 * 60


# --------------------------------------------------------------------------
# Ontario statutory (public) holidays
# https://www.ontario.ca/document/your-guide-employment-standards-act-0/public-holidays
# --------------------------------------------------------------------------
def easter_sunday(year):
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def nth_weekday(year, month, weekday, n):
    """n-th given weekday (0=Mon) of a month, e.g. 3rd Monday of February."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def ontario_stat_holidays(year, move_weekend_to_weekday=True):
    """Return {date: holiday name} for the nine ESA public holidays in Ontario."""
    may_24 = date(year, 5, 24)
    holidays = [
        (date(year, 1, 1), "New Year's Day"),
        (nth_weekday(year, 2, 0, 3), "Family Day"),
        (easter_sunday(year) - timedelta(days=2), "Good Friday"),
        (may_24 - timedelta(days=may_24.weekday()), "Victoria Day"),  # Monday before May 25
        (date(year, 7, 1), "Canada Day"),
        (nth_weekday(year, 9, 0, 1), "Labour Day"),
        (nth_weekday(year, 10, 0, 2), "Thanksgiving Day"),
        (date(year, 12, 25), "Christmas Day"),
        (date(year, 12, 26), "Boxing Day"),
    ]

    result = {}
    for day, name in sorted(holidays):
        if move_weekend_to_weekday and day.weekday() >= 5:
            # Holiday on a weekend -> substitute day off on the next free weekday
            observed = day
            while observed.weekday() >= 5 or observed in result:
                observed += timedelta(days=1)
            result[observed] = f"{name} (observed)"
        else:
            result[day] = name
    return result


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def fail(message):
    raise SystemExit(f"ERROR: {message}")


def check_response(response, what):
    if not (200 <= response.status_code < 300):
        fail(f"{what} failed: {response.status_code} - {response.text}")
    return response.json()


def parse_args():
    parser = argparse.ArgumentParser(description="Fill Teamwork time entries from a Monday up to today.")
    parser.add_argument("--start", help="Start date (a Monday), YYYY-MM-DD. Default: Monday of this week.")
    parser.add_argument("--end", help="End date (inclusive), YYYY-MM-DD. Default: today.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be posted without posting anything.")
    return parser.parse_args()


def local_to_utc(day, time_str, tz):
    local_dt = datetime.datetime.combine(day, datetime.time.fromisoformat(time_str), tzinfo=tz)
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    return utc_dt.strftime("%Y-%m-%d"), utc_dt.strftime("%H:%M:%S")


def minutes_between(start_str, end_str):
    start = datetime.datetime.combine(date.min, datetime.time.fromisoformat(start_str))
    end = datetime.datetime.combine(date.min, datetime.time.fromisoformat(end_str))
    minutes = int((end - start).total_seconds() // 60)
    if minutes <= 0:
        fail(f"time_end {end_str} must be after time_start {start_str}")
    return minutes


def find_project_id(client, project_name):
    data = check_response(client.get_projects({"searchTerm": project_name}), "Getting projects")
    for project in data.get("projects", []):
        if project["name"] == project_name:
            return project["id"]
    fail(f"Project '{project_name}' not found.")


def get_all_pages(fetch, key, what):
    """Call fetch(params) for each page and collect data[key]."""
    items, page = [], 1
    while True:
        data = check_response(fetch({"page": page, "pageSize": 250}), what)
        items.extend(data.get(key, []))
        if not data.get("meta", {}).get("page", {}).get("hasMore"):
            return items
        page += 1


def resolve_task_ids(client, project_id, wanted):
    """wanted: set of (task_list_name, task_name). Returns {(list, task): task_id}."""
    task_lists = get_all_pages(lambda p: client.get_tasks_list(project_id, p), "tasklists", "Getting task lists")
    list_ids = {tl["name"]: tl["id"] for tl in task_lists}

    task_ids = {}
    for list_name in sorted({list_name for list_name, _ in wanted}):
        if list_name not in list_ids:
            fail(f"Task list '{list_name}' not found in project.")
        tasks = get_all_pages(lambda p: client.get_tasks_from_tasks_list(list_ids[list_name], p),
                              "tasks", f"Getting tasks for '{list_name}'")
        for task in tasks:
            if (list_name, task["name"]) in wanted:
                task_ids[(list_name, task["name"])] = task["id"]

    missing = [f"{l} -> {t}" for l, t in wanted if (l, t) not in task_ids]
    if missing:
        fail(f"Tasks not found: {missing}")
    return task_ids


def existing_minutes_by_day(client, user_id, start, end, tz):
    """Minutes you already logged per local date in [start, end]."""
    # Pad by a day on each side: Teamwork stores UTC, we group by local date.
    params_base = {
        "startDate": (start - timedelta(days=1)).isoformat(),
        "endDate": (end + timedelta(days=1)).isoformat(),
        "assignedToUserIds": user_id,
    }
    logs = get_all_pages(lambda p: client.get_time_entries({**params_base, **p}), "timelogs", "Getting existing time entries")

    totals = {}
    for log in logs:
        if log.get("userId") != user_id:
            continue
        logged = datetime.datetime.fromisoformat(log["timeLogged"].replace("Z", "+00:00"))
        local_day = logged.astimezone(tz).date()
        totals[local_day] = totals.get(local_day, 0) + log.get("minutes", 0)
    return totals


def build_payload(project_id, task_id, description, day, time_start, minutes, billable, tz):
    utc_date, utc_time = local_to_utc(day, time_start, tz)
    return {
        "timelog": {
            "description": description,
            "hours": minutes // 60,
            "minutes": minutes % 60,
            "isBillable": billable,
            "isUtc": True,
            "projectId": project_id,
            "taskId": task_id,
            "date": utc_date,
            "time": utc_time,
        }
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    args = parse_args()
    load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

    with open(TIME_ENTRIES_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    tz = ZoneInfo(config.get("timezone", "America/Toronto"))
    today = datetime.datetime.now(tz).date()

    start = date.fromisoformat(args.start) if args.start else today - timedelta(days=today.weekday())
    end = date.fromisoformat(args.end) if args.end else today
    if start.weekday() != 0:
        fail(f"Start date {start} is a {WEEKDAY_NAMES[start.weekday()].title()}, not a Monday.")
    if end < start:
        fail(f"End date {end} is before start date {start}.")

    regular_entries = [e for e in config["time_entries"] if e.get("type", "REGULAR") == "REGULAR"]
    holiday_cfg = config["stat_holiday"]
    move_weekend = holiday_cfg.get("move_weekend_holidays_to_next_weekday", True)

    holidays = {}
    for year in range(start.year, end.year + 1):
        holidays.update(ontario_stat_holidays(year, move_weekend))

    print(f"Teamwork time fill: {start} -> {end}{'  (DRY RUN)' if args.dry_run else ''}")

    api_key = os.getenv("TEAMWORK_API")
    base_url = os.getenv("TEAMWORK_BASEURL")
    if not api_key or not base_url:
        fail("TEAMWORK_API / TEAMWORK_BASEURL missing from .env")
    client = teamwork_client.TeamworkClient(base_url, api_key)

    # Resolve everything up front, before posting anything
    user_id = check_response(client.get_me(), "Getting current user")["person"]["id"]
    project_id = find_project_id(client, config["project_name"])
    wanted = {(e["task_list"], e["task"]) for e in regular_entries}
    wanted.add((holiday_cfg["task_list"], holiday_cfg["task"]))
    task_ids = resolve_task_ids(client, project_id, wanted)
    already_logged = existing_minutes_by_day(client, user_id, start, end, tz)

    # Build the plan: [(day, label, [payloads])]
    plan = []
    day = start
    while day <= end:
        weekday = WEEKDAY_NAMES[day.weekday()]
        if day.weekday() >= 5:
            day += timedelta(days=1)
            continue

        logged = already_logged.get(day, 0)
        if logged:
            note = "" if logged == FULL_DAY_MINUTES else f"  <-- WARNING: {logged / 60:g}h logged, expected 8h"
            print(f"  {day} {weekday[:3]}  SKIP (already has {logged / 60:g}h logged){note}")
            day += timedelta(days=1)
            continue

        if day in holidays:
            name = holidays[day]
            payload = build_payload(
                project_id, task_ids[(holiday_cfg["task_list"], holiday_cfg["task"])], name, day,
                holiday_cfg["time_start"], int(holiday_cfg["hours"] * 60), holiday_cfg.get("billable", False), tz)
            plan.append((day, f"STAT HOLIDAY: {name}", [payload]))
        else:
            payloads = []
            for e in regular_entries:
                if weekday in [d.upper() for d in e["WEEKDAY"]]:
                    payloads.append(build_payload(
                        project_id, task_ids[(e["task_list"], e["task"])], e["description"], day,
                        e["time_start"], minutes_between(e["time_start"], e["time_end"]), e.get("billable", False), tz))
            plan.append((day, "regular", payloads))
        day += timedelta(days=1)

    if not plan:
        print("Nothing to submit.")
        return

    failures = 0
    for day, label, payloads in plan:
        total = sum(p["timelog"]["hours"] * 60 + p["timelog"]["minutes"] for p in payloads)
        print(f"  {day} {WEEKDAY_NAMES[day.weekday()][:3]}  {label}  ({total / 60:g}h)")
        for p in payloads:
            t = p["timelog"]
            line = f"      {t['hours']}h{t['minutes']:02d}m  {t['description']}  [UTC {t['date']} {t['time']}]"
            if args.dry_run:
                print(line)
                continue
            response = client.post_time_entry_from_task(t["taskId"], p)
            if 200 <= response.status_code < 300:
                print(line + "  OK")
            else:
                failures += 1
                print(line + f"  FAILED: {response.status_code} - {response.text}")

    if failures:
        fail(f"{failures} time entr{'y' if failures == 1 else 'ies'} failed to post.")
    print("Dry run complete, nothing posted." if args.dry_run else "Done.")


if __name__ == "__main__":
    main()
