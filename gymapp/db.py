"""SQLite schema and seed data for the gym app."""
import hashlib
import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE, price REAL, guest_passes INTEGER, perks TEXT);
CREATE TABLE IF NOT EXISTS gyms(
    id INTEGER PRIMARY KEY, name TEXT, address TEXT, lat REAL, lon REAL, capacity INTEGER);
CREATE TABLE IF NOT EXISTS gym_hours(
    gym_id INTEGER, dow INTEGER, open TEXT, close TEXT, PRIMARY KEY(gym_id, dow));
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, pw_hash TEXT, salt TEXT,
    role TEXT DEFAULT 'member', member_code TEXT UNIQUE, plan_id INTEGER,
    status TEXT DEFAULT 'active', home_gym_id INTEGER, guest_passes INTEGER DEFAULT 0,
    next_billing TEXT, calorie_goal INTEGER DEFAULT 2200, created TEXT);
CREATE TABLE IF NOT EXISTS checkins(
    id INTEGER PRIMARY KEY, user_id INTEGER, gym_id INTEGER, ts TEXT, guest INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS exercises(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE, muscle TEXT, equipment TEXT);
CREATE TABLE IF NOT EXISTS workouts(
    id INTEGER PRIMARY KEY, user_id INTEGER, started TEXT, finished TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS workout_sets(
    id INTEGER PRIMARY KEY, workout_id INTEGER, exercise_id INTEGER, reps INTEGER, weight REAL);
CREATE TABLE IF NOT EXISTS classes(
    id INTEGER PRIMARY KEY, gym_id INTEGER, title TEXT, instructor TEXT, start_ts TEXT,
    duration INTEGER DEFAULT 30, capacity INTEGER);
CREATE TABLE IF NOT EXISTS class_bookings(
    id INTEGER PRIMARY KEY, class_id INTEGER, user_id INTEGER, UNIQUE(class_id, user_id));
CREATE TABLE IF NOT EXISTS equipment(
    id INTEGER PRIMARY KEY, gym_id INTEGER, name TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS equipment_bookings(
    id INTEGER PRIMARY KEY, equipment_id INTEGER, user_id INTEGER, start_ts TEXT,
    UNIQUE(equipment_id, start_ts));
CREATE TABLE IF NOT EXISTS challenges(
    id INTEGER PRIMARY KEY, title TEXT, metric TEXT, target INTEGER, days INTEGER, badge TEXT);
CREATE TABLE IF NOT EXISTS challenge_members(
    challenge_id INTEGER, user_id INTEGER, joined TEXT, PRIMARY KEY(challenge_id, user_id));
CREATE TABLE IF NOT EXISTS badges(
    user_id INTEGER, badge TEXT, earned TEXT, PRIMARY KEY(user_id, badge));
CREATE TABLE IF NOT EXISTS workout_plans(
    id INTEGER PRIMARY KEY, name TEXT, goal TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS plan_days(
    plan_id INTEGER, day INTEGER, title TEXT, exercises TEXT, PRIMARY KEY(plan_id, day));
CREATE TABLE IF NOT EXISTS user_plan(
    user_id INTEGER PRIMARY KEY, plan_id INTEGER, started TEXT);
CREATE TABLE IF NOT EXISTS foods(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE, calories INTEGER, protein REAL);
CREATE TABLE IF NOT EXISTS food_logs(
    id INTEGER PRIMARY KEY, user_id INTEGER, day TEXT, name TEXT, calories INTEGER, protein REAL);
CREATE TABLE IF NOT EXISTS body_weight(
    id INTEGER PRIMARY KEY, user_id INTEGER, day TEXT, kg REAL);
"""


def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000)
    return digest.hex(), salt


def connect(path="gymapp.db"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 0:
        seed(conn)
    return conn


EXERCISES = [
    ("Bench Press", "Chest", "Barbell"), ("Incline Dumbbell Press", "Chest", "Dumbbell"),
    ("Chest Press Machine", "Chest", "Machine"), ("Lat Pulldown", "Back", "Machine"),
    ("Seated Row", "Back", "Machine"), ("Deadlift", "Back", "Barbell"),
    ("Squat", "Legs", "Smith Machine"), ("Leg Press", "Legs", "Machine"),
    ("Leg Curl", "Legs", "Machine"), ("Calf Raise", "Legs", "Machine"),
    ("Shoulder Press", "Shoulders", "Dumbbell"), ("Lateral Raise", "Shoulders", "Dumbbell"),
    ("Bicep Curl", "Arms", "Dumbbell"), ("Tricep Pushdown", "Arms", "Cable"),
    ("Plank (sec)", "Core", "Bodyweight"), ("Crunch", "Core", "Bodyweight"),
    ("Treadmill (min)", "Cardio", "Treadmill"), ("Elliptical (min)", "Cardio", "Elliptical"),
]
FOODS = [
    ("Egg", 78, 6), ("Oatmeal (1 cup)", 154, 6), ("Chicken Breast (100g)", 165, 31),
    ("Brown Rice (1 cup)", 216, 5), ("Banana", 105, 1.3), ("Protein Shake", 130, 25),
    ("Greek Yogurt", 100, 17), ("Salmon (100g)", 208, 20), ("Apple", 95, 0.5),
    ("Peanut Butter (2 tbsp)", 190, 8), ("Broccoli (1 cup)", 55, 3.7), ("Whole Wheat Bread", 80, 4),
]
GYMS = [
    ("Downtown", "100 Main St", 40.7128, -74.0060, 120, ("05:00", "23:00")),
    ("Riverside", "22 River Rd", 40.7306, -73.9352, 90, ("00:00", "24:00")),
    ("Uptown", "880 Park Ave", 40.7831, -73.9712, 150, ("06:00", "22:00")),
]
EQUIPMENT = [("Treadmill", "Cardio"), ("Treadmill", "Cardio"), ("Elliptical", "Cardio"),
             ("Smith Machine", "Strength"), ("Leg Press", "Strength"), ("Cable Station", "Strength"),
             ("Massage Chair", "Recovery")]
CHALLENGES = [
    ("Show Up 5", "checkins", 5, 14, "Consistency Starter"),
    ("Iron Month", "workouts", 12, 30, "Iron Regular"),
    ("1000 Set Club", "sets", 100, 30, "Set Crusher"),
]
PLANS = [
    ("Classic", 15.0, 0, "Gym access at your home club, equipment & classes"),
    ("Black Card", 29.99, 1, "All clubs, bring a guest, massage chairs, 2 booking slots/day"),
]
WORKOUT_PLANS = [
    ("Beginner Full Body", "General fitness", "3 days a week, simple compound moves", {
        0: ("Full Body A", ["Chest Press Machine", "Seated Row", "Leg Press", "Plank (sec)"]),
        2: ("Full Body B", ["Shoulder Press", "Lat Pulldown", "Leg Curl", "Crunch"]),
        4: ("Full Body C", ["Incline Dumbbell Press", "Seated Row", "Squat", "Treadmill (min)"])}),
    ("Push Pull Legs", "Muscle gain", "Classic 3-day split", {
        0: ("Push", ["Bench Press", "Shoulder Press", "Lateral Raise", "Tricep Pushdown"]),
        2: ("Pull", ["Deadlift", "Lat Pulldown", "Seated Row", "Bicep Curl"]),
        4: ("Legs", ["Squat", "Leg Press", "Leg Curl", "Calf Raise"])}),
    ("Fat Loss Cardio", "Weight loss", "Cardio focus with core work", {
        0: ("Cardio A", ["Treadmill (min)", "Plank (sec)"]),
        1: ("Cardio B", ["Elliptical (min)", "Crunch"]),
        3: ("Cardio C", ["Treadmill (min)", "Elliptical (min)"]),
        5: ("Strength", ["Squat", "Chest Press Machine", "Seated Row"])}),
]


def seed(conn):
    for n, p, g, d in PLANS:
        conn.execute("INSERT INTO plans(name,price,guest_passes,perks) VALUES(?,?,?,?)", (n, p, g, d))
    conn.executemany("INSERT INTO exercises(name,muscle,equipment) VALUES(?,?,?)", EXERCISES)
    conn.executemany("INSERT INTO foods(name,calories,protein) VALUES(?,?,?)", FOODS)
    conn.executemany("INSERT INTO challenges(title,metric,target,days,badge) VALUES(?,?,?,?,?)", CHALLENGES)
    for name, addr, lat, lon, cap, (o, c) in GYMS:
        gid = conn.execute("INSERT INTO gyms(name,address,lat,lon,capacity) VALUES(?,?,?,?,?)",
                           (name, addr, lat, lon, cap)).lastrowid
        for dow in range(7):
            conn.execute("INSERT INTO gym_hours VALUES(?,?,?,?)", (gid, dow, o, c))
        for i, (en, kind) in enumerate(EQUIPMENT):
            conn.execute("INSERT INTO equipment(gym_id,name,kind) VALUES(?,?,?)",
                         (gid, f"{en} #{i + 1}", kind))
    for name, goal, desc, days in WORKOUT_PLANS:
        pid = conn.execute("INSERT INTO workout_plans(name,goal,description) VALUES(?,?,?)",
                           (name, goal, desc)).lastrowid
        for dow, (title, ex) in days.items():
            conn.execute("INSERT INTO plan_days VALUES(?,?,?,?)", (pid, dow, title, json.dumps(ex)))
    h, s = hash_password("admin123")
    conn.execute("INSERT INTO users(name,email,pw_hash,salt,role,member_code,plan_id,home_gym_id,created)"
                 " VALUES('Admin','admin@gym.local',?,?,'admin','GYM0000000',2,1,datetime('now'))", (h, s))
    conn.commit()
