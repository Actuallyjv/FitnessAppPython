# Gym App (Kivy)

A Planet Fitness-style mobile gym app written in Python with Kivy and SQLite.

## Features
- **Member check-in**: Code 39 barcode membership card, check-in by club, guest passes (Black Card), visit history, streaks
- **Workout tracking**: exercise library, log sets/reps/weight, history, personal records, body-weight log
- **Workout plans & nutrition**: 3 starter programs with a "today's session" card, calorie/protein tracking with quick-add foods and a daily goal
- **Class & equipment booking**: 7-day class schedule with capacity limits and clash detection; 30-minute equipment reservations (Classic: 1/day, Black Card: 2/day, massage chairs Black Card only)
- **Gym locator & hours**: club list with open/closed, hours and live crowd level; set a home club
- **Membership management**: Classic / Black Card, switch plan, freeze, cancel, reactivate
- **Challenges & rewards**: join challenges, progress bars, badges, 30-day leaderboard
- **Admin dashboard**: stats, member search and freeze/activate, create/delete classes, rosters, recent check-ins

## Run
```
pip install -r requirements.txt
python main.py
```
Demo admin login: `admin@gym.local` / `admin123` (change before any real use). Data lives in `gymapp.db`.

## Test
```
pip install pytest
python -m pytest
```
All business rules live in `gymapp/services.py` (no UI imports) and are covered by `tests/`.

## Android
`buildozer.spec` is included: `buildozer android debug` (Linux/WSL, not tested here).

## Notes / MVP limits
- Billing is simulated (no payment processing); crowd level is derived from app check-ins.
- Local single-device database; there is no server sync.
- `FitnessApp.py` is the original PyQt measurements stub and is not used by the app.
