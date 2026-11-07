"""Business logic for the gym app. No UI imports, so it is fully testable."""
import json
import math
import re
import secrets
from datetime import date, datetime, timedelta

from .db import hash_password

FMT = "%Y-%m-%d %H:%M"
DAY = "%Y-%m-%d"


class GymError(Exception):
    """A user-facing validation or rule error."""


def _ts(dt):
    return dt.strftime(FMT)


def _parse(s):
    return datetime.strptime(s, FMT)


class GymService:
    def __init__(self, conn):
        self.db = conn

    # ---------- helpers ----------
    def _one(self, sql, args=()):
        return self.db.execute(sql, args).fetchone()

    def _all(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def user(self, user_id):
        r = self._one("SELECT * FROM users WHERE id=?", (user_id,))
        if not r:
            raise GymError("User not found")
        return dict(r)

    def _require_admin(self, user_id):
        if self.user(user_id)["role"] != "admin":
            raise GymError("Admin access required")

    def _require_active(self, user_id):
        u = self.user(user_id)
        if u["status"] != "active":
            raise GymError(f"Membership is {u['status']}")
        return u

    # ---------- accounts ----------
    def register(self, name, email, password, plan_id=1, home_gym_id=1, now=None):
        now = now or datetime.now()
        email = email.strip().lower()
        if not name.strip():
            raise GymError("Name is required")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise GymError("Enter a valid email")
        if len(password) < 6:
            raise GymError("Password must be at least 6 characters")
        if self._one("SELECT 1 FROM users WHERE email=?", (email,)):
            raise GymError("Email already registered")
        plan = self._one("SELECT * FROM plans WHERE id=?", (plan_id,))
        if not plan or not self._one("SELECT 1 FROM gyms WHERE id=?", (home_gym_id,)):
            raise GymError("Invalid plan or gym")
        while True:
            code = "GYM%07d" % secrets.randbelow(10**7)
            if not self._one("SELECT 1 FROM users WHERE member_code=?", (code,)):
                break
        h, s = hash_password(password)
        cur = self.db.execute(
            "INSERT INTO users(name,email,pw_hash,salt,member_code,plan_id,home_gym_id,guest_passes,"
            "next_billing,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (name.strip(), email, h, s, code, plan_id, home_gym_id, plan["guest_passes"],
             (now + timedelta(days=30)).strftime(DAY), _ts(now)))
        self.db.commit()
        return self.user(cur.lastrowid)

    def login(self, email, password):
        r = self._one("SELECT * FROM users WHERE email=?", (email.strip().lower(),))
        if not r:
            return None
        h, _ = hash_password(password, r["salt"])
        return dict(r) if secrets.compare_digest(h, r["pw_hash"]) else None

    # ---------- gyms ----------
    def gyms(self):
        return self._all("SELECT * FROM gyms ORDER BY name")

    def nearest_gyms(self, lat, lon):
        out = self.gyms()
        for g in out:
            p1, p2 = math.radians(lat), math.radians(g["lat"])
            a = (math.sin((p2 - p1) / 2) ** 2 +
                 math.cos(p1) * math.cos(p2) * math.sin(math.radians(g["lon"] - lon) / 2) ** 2)
            g["km"] = 6371 * 2 * math.asin(math.sqrt(a))
        return sorted(out, key=lambda g: g["km"])

    def hours(self, gym_id, dow):
        r = self._one("SELECT open, close FROM gym_hours WHERE gym_id=? AND dow=?", (gym_id, dow))
        return (r["open"], r["close"]) if r else None

    def is_open(self, gym_id, now=None):
        now = now or datetime.now()
        h = self.hours(gym_id, now.weekday())
        if not h:
            return False
        cur = now.strftime("%H:%M")
        return h[0] <= cur < h[1] or h[1] == "24:00"

    def crowd(self, gym_id, now=None):
        """Busy-ness from check-ins in the last 90 minutes vs capacity/3."""
        now = now or datetime.now()
        g = self._one("SELECT capacity FROM gyms WHERE id=?", (gym_id,))
        n = self._one("SELECT COUNT(*) c FROM checkins WHERE gym_id=? AND ts>? AND ts<=?",
                      (gym_id, _ts(now - timedelta(minutes=90)), _ts(now)))["c"]
        pct = min(100, round(100 * n / max(1, g["capacity"] / 3)))
        label = "Not busy" if pct < 40 else "Moderate" if pct < 75 else "Busy"
        return {"count": n, "percent": pct, "label": label}

    # ---------- check-in ----------
    def checkin(self, user_id, gym_id, now=None, guest=False):
        now = now or datetime.now()
        u = self._require_active(user_id)
        if not self.is_open(gym_id, now):
            raise GymError("This club is currently closed")
        plan = self._one("SELECT * FROM plans WHERE id=?", (u["plan_id"],))
        if plan["name"] == "Classic" and gym_id != u["home_gym_id"]:
            raise GymError("Classic members can only check in at their home club")
        recent = self._one("SELECT 1 FROM checkins WHERE user_id=? AND guest=? AND ts>? AND ts<=?",
                           (user_id, int(guest), _ts(now - timedelta(minutes=60)), _ts(now)))
        if recent:
            raise GymError("Already checked in within the last hour")
        if guest:
            if u["guest_passes"] < 1:
                raise GymError("No guest passes available (Black Card perk)")
            self.db.execute("UPDATE users SET guest_passes=guest_passes-1 WHERE id=?", (user_id,))
        self.db.execute("INSERT INTO checkins(user_id,gym_id,ts,guest) VALUES(?,?,?,?)",
                        (user_id, gym_id, _ts(now), int(guest)))
        self.db.commit()
        return self.evaluate_badges(user_id, now)

    def checkin_history(self, user_id, limit=20):
        return self._all("SELECT c.*, g.name gym FROM checkins c JOIN gyms g ON g.id=c.gym_id "
                         "WHERE user_id=? ORDER BY ts DESC LIMIT ?", (user_id, limit))

    def streak(self, user_id, today=None):
        today = (today or date.today())
        days = {r["d"] for r in self._all(
            "SELECT DISTINCT substr(ts,1,10) d FROM checkins WHERE user_id=? AND guest=0", (user_id,))}
        d = today if today.strftime(DAY) in days else today - timedelta(days=1)
        n = 0
        while d.strftime(DAY) in days:
            n += 1
            d -= timedelta(days=1)
        return n

    # ---------- workouts ----------
    def exercises(self, muscle=None):
        if muscle:
            return self._all("SELECT * FROM exercises WHERE muscle=? ORDER BY name", (muscle,))
        return self._all("SELECT * FROM exercises ORDER BY muscle, name")

    def start_workout(self, user_id, now=None, notes=""):
        self._require_active(user_id)
        cur = self.db.execute("INSERT INTO workouts(user_id,started,notes) VALUES(?,?,?)",
                              (user_id, _ts(now or datetime.now()), notes))
        self.db.commit()
        return cur.lastrowid

    def _own_workout(self, user_id, workout_id):
        w = self._one("SELECT * FROM workouts WHERE id=? AND user_id=?", (workout_id, user_id))
        if not w:
            raise GymError("Workout not found")
        return w

    def add_set(self, user_id, workout_id, exercise_id, reps, weight):
        w = self._own_workout(user_id, workout_id)
        if w["finished"]:
            raise GymError("Workout already finished")
        if reps <= 0 or weight < 0:
            raise GymError("Reps must be positive and weight cannot be negative")
        if not self._one("SELECT 1 FROM exercises WHERE id=?", (exercise_id,)):
            raise GymError("Unknown exercise")
        cur = self.db.execute("INSERT INTO workout_sets(workout_id,exercise_id,reps,weight) VALUES(?,?,?,?)",
                              (workout_id, exercise_id, reps, weight))
        self.db.commit()
        return cur.lastrowid

    def finish_workout(self, user_id, workout_id, now=None):
        self._own_workout(user_id, workout_id)
        self.db.execute("UPDATE workouts SET finished=? WHERE id=?", (_ts(now or datetime.now()), workout_id))
        self.db.commit()
        return self.evaluate_badges(user_id, now)

    def workout_sets(self, workout_id):
        return self._all("SELECT s.*, e.name exercise FROM workout_sets s JOIN exercises e "
                         "ON e.id=s.exercise_id WHERE workout_id=? ORDER BY s.id", (workout_id,))

    def workout_history(self, user_id, limit=15):
        rows = self._all("SELECT w.*, (SELECT COUNT(*) FROM workout_sets WHERE workout_id=w.id) sets,"
                         " (SELECT COALESCE(SUM(reps*weight),0) FROM workout_sets WHERE workout_id=w.id) volume "
                         "FROM workouts w WHERE user_id=? ORDER BY started DESC LIMIT ?", (user_id, limit))
        return rows

    def personal_records(self, user_id):
        return self._all(
            "SELECT e.name exercise, MAX(s.weight) weight, "
            "(SELECT MAX(reps) FROM workout_sets s2 JOIN workouts w2 ON w2.id=s2.workout_id "
            " WHERE w2.user_id=? AND s2.exercise_id=e.id AND s2.weight=MAX(s.weight)) reps "
            "FROM workout_sets s JOIN workouts w ON w.id=s.workout_id JOIN exercises e ON e.id=s.exercise_id "
            "WHERE w.user_id=? GROUP BY e.id ORDER BY weight DESC", (user_id, user_id))

    # ---------- classes ----------
    def classes(self, gym_id, now=None, days=7):
        now = now or datetime.now()
        rows = self._all(
            "SELECT c.*, (SELECT COUNT(*) FROM class_bookings WHERE class_id=c.id) booked "
            "FROM classes c WHERE gym_id=? AND start_ts>? AND start_ts<=? ORDER BY start_ts",
            (gym_id, _ts(now), _ts(now + timedelta(days=days))))
        return rows

    def create_class(self, admin_id, gym_id, title, instructor, start, capacity, duration=30):
        self._require_admin(admin_id)
        if not title.strip() or capacity < 1:
            raise GymError("Title and a positive capacity are required")
        cur = self.db.execute("INSERT INTO classes(gym_id,title,instructor,start_ts,duration,capacity) "
                              "VALUES(?,?,?,?,?,?)", (gym_id, title.strip(), instructor, _ts(start), duration, capacity))
        self.db.commit()
        return cur.lastrowid

    def delete_class(self, admin_id, class_id):
        self._require_admin(admin_id)
        self.db.execute("DELETE FROM class_bookings WHERE class_id=?", (class_id,))
        self.db.execute("DELETE FROM classes WHERE id=?", (class_id,))
        self.db.commit()

    def book_class(self, user_id, class_id, now=None):
        now = now or datetime.now()
        self._require_active(user_id)
        c = self._one("SELECT * FROM classes WHERE id=?", (class_id,))
        if not c:
            raise GymError("Class not found")
        if c["start_ts"] <= _ts(now):
            raise GymError("Class has already started")
        if self._one("SELECT 1 FROM class_bookings WHERE class_id=? AND user_id=?", (class_id, user_id)):
            raise GymError("Already booked")
        booked = self._one("SELECT COUNT(*) n FROM class_bookings WHERE class_id=?", (class_id,))["n"]
        if booked >= c["capacity"]:
            raise GymError("Class is full")
        clash = self._one(
            "SELECT 1 FROM class_bookings b JOIN classes c2 ON c2.id=b.class_id WHERE b.user_id=? AND c2.start_ts=?",
            (user_id, c["start_ts"]))
        if clash:
            raise GymError("You have another class at this time")
        self.db.execute("INSERT INTO class_bookings(class_id,user_id) VALUES(?,?)", (class_id, user_id))
        self.db.commit()

    def cancel_class(self, user_id, class_id):
        self.db.execute("DELETE FROM class_bookings WHERE class_id=? AND user_id=?", (class_id, user_id))
        self.db.commit()

    def my_classes(self, user_id, now=None):
        return self._all("SELECT c.*, g.name gym FROM class_bookings b JOIN classes c ON c.id=b.class_id "
                         "JOIN gyms g ON g.id=c.gym_id WHERE b.user_id=? AND c.start_ts>? ORDER BY c.start_ts",
                         (user_id, _ts(now or datetime.now())))

    def roster(self, admin_id, class_id):
        self._require_admin(admin_id)
        return self._all("SELECT u.name, u.email, u.member_code FROM class_bookings b JOIN users u "
                         "ON u.id=b.user_id WHERE b.class_id=? ORDER BY u.name", (class_id,))

    # ---------- equipment (30-minute slots) ----------
    def equipment(self, gym_id):
        return self._all("SELECT * FROM equipment WHERE gym_id=? ORDER BY kind, name", (gym_id,))

    def equipment_slots(self, equipment_id, day, now=None):
        """Open 30-minute slots on `day` (a date) for a piece of equipment."""
        now = now or datetime.now()
        eq = self._one("SELECT * FROM equipment WHERE id=?", (equipment_id,))
        if not eq:
            raise GymError("Equipment not found")
        h = self.hours(eq["gym_id"], day.weekday())
        if not h:
            return []
        end_h = 24 * 60 if h[1] == "24:00" else int(h[1][:2]) * 60 + int(h[1][3:])
        t = int(h[0][:2]) * 60 + int(h[0][3:])
        taken = {r["start_ts"] for r in self._all(
            "SELECT start_ts FROM equipment_bookings WHERE equipment_id=? AND substr(start_ts,1,10)=?",
            (equipment_id, day.strftime(DAY)))}
        out = []
        while t + 30 <= end_h:
            slot = datetime(day.year, day.month, day.day) + timedelta(minutes=t)
            if slot > now and _ts(slot) not in taken:
                out.append(slot)
            t += 30
        return out

    def book_equipment(self, user_id, equipment_id, start, now=None):
        now = now or datetime.now()
        u = self._require_active(user_id)
        eq = self._one("SELECT * FROM equipment WHERE id=?", (equipment_id,))
        if not eq:
            raise GymError("Equipment not found")
        if start <= now:
            raise GymError("Pick a future time")
        if start.minute not in (0, 30) or start.second:
            raise GymError("Bookings start on the hour or half hour")
        if eq["kind"] == "Recovery":
            plan = self._one("SELECT name FROM plans WHERE id=?", (u["plan_id"],))["name"]
            if plan != "Black Card":
                raise GymError("Massage chairs are a Black Card perk")
        if start not in self.equipment_slots(equipment_id, start.date(), now):
            raise GymError("That slot is unavailable")
        plan = self._one("SELECT name FROM plans WHERE id=?", (u["plan_id"],))["name"]
        limit = 2 if plan == "Black Card" else 1
        day_count = self._one("SELECT COUNT(*) n FROM equipment_bookings WHERE user_id=? AND substr(start_ts,1,10)=?",
                              (user_id, start.strftime(DAY)))["n"]
        if day_count >= limit:
            raise GymError(f"Your plan allows {limit} equipment booking(s) per day")
        self.db.execute("INSERT INTO equipment_bookings(equipment_id,user_id,start_ts) VALUES(?,?,?)",
                        (equipment_id, user_id, _ts(start)))
        self.db.commit()

    def cancel_equipment(self, user_id, booking_id):
        self.db.execute("DELETE FROM equipment_bookings WHERE id=? AND user_id=?", (booking_id, user_id))
        self.db.commit()

    def my_equipment(self, user_id, now=None):
        return self._all("SELECT b.id, b.start_ts, e.name, g.name gym FROM equipment_bookings b "
                         "JOIN equipment e ON e.id=b.equipment_id JOIN gyms g ON g.id=e.gym_id "
                         "WHERE b.user_id=? AND b.start_ts>? ORDER BY b.start_ts",
                         (user_id, _ts(now or datetime.now())))

    # ---------- membership ----------
    def plans(self):
        return self._all("SELECT * FROM plans ORDER BY price")

    def change_plan(self, user_id, plan_id):
        plan = self._one("SELECT * FROM plans WHERE id=?", (plan_id,))
        if not plan:
            raise GymError("Unknown plan")
        self._require_active(user_id)
        self.db.execute("UPDATE users SET plan_id=?, guest_passes=? WHERE id=?",
                        (plan_id, plan["guest_passes"], user_id))
        self.db.commit()

    def set_status(self, user_id, status, now=None):
        if status not in ("active", "frozen", "cancelled"):
            raise GymError("Invalid status")
        u = self.user(user_id)
        if u["status"] == "cancelled" and status != "active":
            raise GymError("Cancelled memberships can only be reactivated")
        nb = u["next_billing"]
        if status == "active" and u["status"] != "active":
            nb = ((now or datetime.now()) + timedelta(days=30)).strftime(DAY)
        self.db.execute("UPDATE users SET status=?, next_billing=? WHERE id=?", (status, nb, user_id))
        self.db.commit()

    def update_profile(self, user_id, home_gym_id=None, calorie_goal=None):
        if home_gym_id is not None:
            if not self._one("SELECT 1 FROM gyms WHERE id=?", (home_gym_id,)):
                raise GymError("Unknown gym")
            self.db.execute("UPDATE users SET home_gym_id=? WHERE id=?", (home_gym_id, user_id))
        if calorie_goal is not None:
            if not 800 <= calorie_goal <= 6000:
                raise GymError("Calorie goal must be between 800 and 6000")
            self.db.execute("UPDATE users SET calorie_goal=? WHERE id=?", (calorie_goal, user_id))
        self.db.commit()

    # ---------- challenges & badges ----------
    def challenges(self, user_id, now=None):
        now = now or datetime.now()
        out = self._all("SELECT c.*, m.joined FROM challenges c LEFT JOIN challenge_members m "
                        "ON m.challenge_id=c.id AND m.user_id=?", (user_id,))
        for c in out:
            c["progress"] = self._progress(user_id, c)
            if c["joined"]:
                c["ends"] = (_parse(c["joined"]) + timedelta(days=c["days"]))
                c["expired"] = c["ends"] < now and c["progress"] < c["target"]
        return out

    def _progress(self, user_id, c):
        if not c.get("joined"):
            return 0
        since = c["joined"]
        end = _ts(_parse(since) + timedelta(days=c["days"]))
        q = {"checkins": "SELECT COUNT(DISTINCT substr(ts,1,10)) n FROM checkins WHERE user_id=? AND guest=0 AND ts>=? AND ts<=?",
             "workouts": "SELECT COUNT(*) n FROM workouts WHERE user_id=? AND finished IS NOT NULL AND started>=? AND started<=?",
             "sets": "SELECT COUNT(*) n FROM workout_sets s JOIN workouts w ON w.id=s.workout_id "
                     "WHERE w.user_id=? AND w.started>=? AND w.started<=?"}[c["metric"]]
        return min(c["target"], self._one(q, (user_id, since, end))["n"])

    def join_challenge(self, user_id, challenge_id, now=None):
        self._require_active(user_id)
        if not self._one("SELECT 1 FROM challenges WHERE id=?", (challenge_id,)):
            raise GymError("Challenge not found")
        self.db.execute("INSERT OR IGNORE INTO challenge_members VALUES(?,?,?)",
                        (challenge_id, user_id, _ts(now or datetime.now())))
        self.db.commit()

    def evaluate_badges(self, user_id, now=None):
        """Award badges for completed challenges; returns newly earned badge names."""
        now = now or datetime.now()
        new = []
        for c in self.challenges(user_id, now):
            if c["joined"] and c["progress"] >= c["target"]:
                cur = self.db.execute("INSERT OR IGNORE INTO badges VALUES(?,?,?)",
                                      (user_id, c["badge"], _ts(now)))
                if cur.rowcount:
                    new.append(c["badge"])
        self.db.commit()
        return new

    def badges(self, user_id):
        return self._all("SELECT * FROM badges WHERE user_id=? ORDER BY earned", (user_id,))

    def leaderboard(self, since_days=30, now=None, limit=10):
        now = now or datetime.now()
        return self._all(
            "SELECT u.name, COUNT(DISTINCT substr(c.ts,1,10)) visits FROM checkins c JOIN users u ON u.id=c.user_id "
            "WHERE c.ts>? AND c.guest=0 AND u.role='member' GROUP BY u.id ORDER BY visits DESC, u.name LIMIT ?",
            (_ts(now - timedelta(days=since_days)), limit))

    # ---------- workout plans ----------
    def workout_plans(self):
        return self._all("SELECT * FROM workout_plans ORDER BY id")

    def plan_schedule(self, plan_id):
        rows = self._all("SELECT * FROM plan_days WHERE plan_id=? ORDER BY day", (plan_id,))
        for r in rows:
            r["exercises"] = json.loads(r["exercises"])
        return rows

    def activate_plan(self, user_id, plan_id, now=None):
        if not self._one("SELECT 1 FROM workout_plans WHERE id=?", (plan_id,)):
            raise GymError("Plan not found")
        self.db.execute("INSERT OR REPLACE INTO user_plan VALUES(?,?,?)",
                        (user_id, plan_id, _ts(now or datetime.now())))
        self.db.commit()

    def active_plan(self, user_id):
        r = self._one("SELECT p.* FROM user_plan up JOIN workout_plans p ON p.id=up.plan_id WHERE up.user_id=?",
                      (user_id,))
        return dict(r) if r else None

    def todays_session(self, user_id, today=None):
        p = self.active_plan(user_id)
        if not p:
            return None
        dow = (today or date.today()).weekday()
        for d in self.plan_schedule(p["id"]):
            if d["day"] == dow:
                return {"plan": p["name"], **d}
        return {"plan": p["name"], "title": "Rest day", "exercises": [], "day": dow}

    # ---------- nutrition ----------
    def foods(self):
        return self._all("SELECT * FROM foods ORDER BY name")

    def log_food(self, user_id, name, calories, protein=0, day=None):
        if not name.strip() or calories < 0 or protein < 0:
            raise GymError("Enter a food name and non-negative numbers")
        cur = self.db.execute("INSERT INTO food_logs(user_id,day,name,calories,protein) VALUES(?,?,?,?,?)",
                              (user_id, (day or date.today()).strftime(DAY), name.strip(), calories, protein))
        self.db.commit()
        return cur.lastrowid

    def delete_food(self, user_id, log_id):
        self.db.execute("DELETE FROM food_logs WHERE id=? AND user_id=?", (log_id, user_id))
        self.db.commit()

    def nutrition_day(self, user_id, day=None):
        d = (day or date.today()).strftime(DAY)
        items = self._all("SELECT * FROM food_logs WHERE user_id=? AND day=? ORDER BY id", (user_id, d))
        goal = self.user(user_id)["calorie_goal"]
        cals = sum(i["calories"] for i in items)
        return {"items": items, "calories": cals, "protein": sum(i["protein"] for i in items),
                "goal": goal, "remaining": goal - cals}

    def log_weight(self, user_id, kg, day=None):
        if not 20 <= kg <= 400:
            raise GymError("Enter a weight between 20 and 400 kg")
        d = (day or date.today()).strftime(DAY)
        self.db.execute("DELETE FROM body_weight WHERE user_id=? AND day=?", (user_id, d))
        self.db.execute("INSERT INTO body_weight(user_id,day,kg) VALUES(?,?,?)", (user_id, d, kg))
        self.db.commit()

    def weight_history(self, user_id, limit=30):
        return self._all("SELECT day, kg FROM body_weight WHERE user_id=? ORDER BY day DESC LIMIT ?",
                         (user_id, limit))

    # ---------- admin ----------
    def admin_stats(self, admin_id, now=None):
        self._require_admin(admin_id)
        now = now or datetime.now()
        today = now.strftime(DAY)
        return {
            "members": self._one("SELECT COUNT(*) n FROM users WHERE role='member'")["n"],
            "active": self._one("SELECT COUNT(*) n FROM users WHERE role='member' AND status='active'")["n"],
            "checkins_today": self._one("SELECT COUNT(*) n FROM checkins WHERE substr(ts,1,10)=?", (today,))["n"],
            "by_plan": self._all("SELECT p.name, COUNT(u.id) n FROM plans p LEFT JOIN users u "
                                 "ON u.plan_id=p.id AND u.role='member' GROUP BY p.id"),
            "monthly_revenue": self._one(
                "SELECT COALESCE(SUM(p.price),0) r FROM users u JOIN plans p ON p.id=u.plan_id "
                "WHERE u.role='member' AND u.status='active'")["r"],
        }

    def list_members(self, admin_id, search=""):
        self._require_admin(admin_id)
        like = f"%{search.strip()}%"
        return self._all("SELECT u.id, u.name, u.email, u.member_code, u.status, p.name plan FROM users u "
                         "JOIN plans p ON p.id=u.plan_id WHERE u.role='member' AND "
                         "(u.name LIKE ? OR u.email LIKE ? OR u.member_code LIKE ?) ORDER BY u.name",
                         (like, like, like))

    def admin_set_status(self, admin_id, user_id, status):
        self._require_admin(admin_id)
        self.set_status(user_id, status)

    def recent_checkins(self, admin_id, limit=20):
        self._require_admin(admin_id)
        return self._all("SELECT c.ts, c.guest, u.name, g.name gym FROM checkins c JOIN users u ON u.id=c.user_id "
                         "JOIN gyms g ON g.id=c.gym_id ORDER BY c.ts DESC LIMIT ?", (limit,))

    def all_classes(self, admin_id, now=None):
        self._require_admin(admin_id)
        return self._all("SELECT c.*, g.name gym, (SELECT COUNT(*) FROM class_bookings WHERE class_id=c.id) booked "
                         "FROM classes c JOIN gyms g ON g.id=c.gym_id WHERE c.start_ts>? ORDER BY c.start_ts",
                         (_ts(now or datetime.now()),))

    def seed_demo_classes(self, admin_id, now=None):
        """Create a week of sample classes if none exist."""
        if self._one("SELECT 1 FROM classes"):
            return
        now = (now or datetime.now()).replace(minute=0, second=0, microsecond=0)
        titles = [("PE@PF Circuit", "Sam"), ("Core Blast", "Jo"), ("Mobility Flow", "Riley"),
                  ("Cardio Sculpt", "Alex")]
        for g in self.gyms():
            for d in range(1, 8):
                for i, (t, inst) in enumerate(titles[:3 if d % 2 else 4]):
                    start = (now + timedelta(days=d)).replace(hour=7 + i * 4)
                    self.create_class(admin_id, g["id"], t, inst, start, 15)
