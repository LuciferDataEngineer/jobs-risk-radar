"""Shared column names and geography labels."""

from __future__ import annotations

STATE_NAMES = {
    "1": "New South Wales",
    "2": "Victoria",
    "3": "Queensland",
    "4": "South Australia",
    "5": "Western Australia",
    "6": "Tasmania",
    "7": "Northern Territory",
    "8": "Australian Capital Territory",
    "AUS": "Australia",
}

# Economic columns stored in the offline feature table and retrieved point-in-time.
FEATURE_COLUMNS = [
    "unemp_rate",
    "unemp_rate_lag3",
    "unemp_rate_lag12",
    "delta_3",
    "delta_12",
    "usual_next_quarter_change",
    "participation_rate",
    "participation_delta_3",
    "youth_unemp_rate",
    "youth_delta_3",
    "employment_growth_3",
    "vacancies_000",
    "vacancies_yoy",
    "approvals",
    "approvals_yoy",
    "cash_rate",
    "cash_delta_3",
    "state_unemp_rate",
    "state_unemp_delta_3",
    "state_rate_official",
]

# A material rise is three tenths of a percentage point over the next quarter.
MATERIAL_RISE = 0.3
