"""Mobile-first web version of the gym app. Reuses gymapp.services (same rules as the Kivy app)."""
import os
import secrets
import sys
from datetime import date, datetime, timedelta

from flask import Flask, g, jsonify, request, send_from_directory, session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gymapp.db import connect  # noqa: E402
from gymapp.services import FMT, GymError, GymService  # noqa: E402

DB = os.environ.get("GYM_DB", "gymapp.db")
app = Flask(__name__, static_folder="static", static_url_path="")


def _secret():
    path = DB + ".secret" if DB != ":memory:" else None
    if path and os.path.exists(path):
        return open(path).read()
    key = secrets.token_hex(32)
    if path:
        with open(path, "w") as f:
            f.write(key)
    return key


app.secret_key = os.environ.get("GYM_SECRET") or _secret()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


def svc():
    if "svc" not in g:
        g.svc = GymService(connect(DB))
    return g.svc


@app.teardown_appcontext
def _close(_):
    s = g.pop("svc", None)
    if s:
        s.db.close()


def _clean(u):
    return {k: v for k, v in u.items() if k not in ("pw_hash", "salt")}


def _dt(s):
    return datetime.strptime(s, FMT)


def me_payload(s, uid):
    u = s.user(uid)
    plan = [p for p in s.plans() if p["id"] == u["plan_id"]][0]
    return {"user": _clean(u), "plan": plan, "streak": s.streak(uid), "badges": s.badges(uid),
            "today": s.todays_session(uid), "history": s.checkin_history(uid, 5), "gyms": s.gyms()}


def open_workout(s, uid):
    r = s._one("SELECT id FROM workouts WHERE user_id=? AND finished IS NULL ORDER BY id DESC LIMIT 1", (uid,))
    return r["id"] if r else None


def train_payload(s, uid):
    wid = open_workout(s, uid)
    return {"exercises": s.exercises(), "workout_id": wid, "sets": s.workout_sets(wid) if wid else [],
            "history": s.workout_history(uid, 8), "prs": s.personal_records(uid),
            "plans": [{**p, "days": s.plan_schedule(p["id"])} for p in s.workout_plans()],
            "active_plan": s.active_plan(uid), "nutrition": s.nutrition_day(uid), "foods": s.foods(),
            "weights": s.weight_history(uid, 10)}


def book_payload(s, uid, gym_id):
    return {"classes": s.classes(gym_id), "mine": s.my_classes(uid), "equipment": s.equipment(gym_id),
            "my_equipment": s.my_equipment(uid)}


def gyms_payload(s, uid):
    now = datetime.now()
    out = []
    for gy in s.gyms():
        out.append({**gy, "open": s.is_open(gy["id"], now), "crowd": s.crowd(gy["id"], now),
                    "hours": s.hours(gy["id"], now.weekday())})
    return out


def more_payload(s, uid):
    return {"plans": s.plans(), "challenges": s.challenges(uid), "leaderboard": s.leaderboard()}


def admin_payload(s, uid, q=""):
    return {"stats": s.admin_stats(uid), "members": s.list_members(uid, q)[:20],
            "classes": s.all_classes(uid)[:15], "recent": s.recent_checkins(uid, 8), "gyms": s.gyms()}


# name -> fn(service, user_id, data). All require a signed-in user except register/login.
ACTIONS = {
    "me": lambda s, u, d: me_payload(s, u),
    "train": lambda s, u, d: train_payload(s, u),
    "book": lambda s, u, d: book_payload(s, u, int(d["gym_id"])),
    "gyms": lambda s, u, d: gyms_payload(s, u),
    "more": lambda s, u, d: more_payload(s, u),
    "checkin": lambda s, u, d: {"badges": s.checkin(u, int(d["gym_id"]), guest=bool(d.get("guest")))},
    "workout_start": lambda s, u, d: {"id": s.start_workout(u)},
    "workout_set": lambda s, u, d: s.add_set(u, int(d["workout_id"]), int(d["exercise_id"]),
                                             int(d["reps"]), float(d.get("weight") or 0)),
    "workout_finish": lambda s, u, d: {"badges": s.finish_workout(u, int(d["workout_id"]))},
    "plan_activate": lambda s, u, d: s.activate_plan(u, int(d["plan_id"])),
    "food_add": lambda s, u, d: s.log_food(u, d["name"], int(d["calories"]), float(d.get("protein") or 0)),
    "food_delete": lambda s, u, d: s.delete_food(u, int(d["id"])),
    "goal": lambda s, u, d: s.update_profile(u, calorie_goal=int(d["goal"])),
    "weight": lambda s, u, d: s.log_weight(u, float(d["kg"])),
    "class_book": lambda s, u, d: s.book_class(u, int(d["id"])),
    "class_cancel": lambda s, u, d: s.cancel_class(u, int(d["id"])),
    "slots": lambda s, u, d: [x.strftime(FMT) for x in s.equipment_slots(
        int(d["equipment_id"]), date.fromisoformat(d["day"]))],
    "equip_book": lambda s, u, d: s.book_equipment(u, int(d["equipment_id"]), _dt(d["start"])),
    "equip_cancel": lambda s, u, d: s.cancel_equipment(u, int(d["id"])),
    "home": lambda s, u, d: s.update_profile(u, home_gym_id=int(d["gym_id"])),
    "status": lambda s, u, d: s.set_status(u, d["status"]),
    "plan_change": lambda s, u, d: s.change_plan(u, int(d["plan_id"])),
    "challenge_join": lambda s, u, d: s.join_challenge(u, int(d["id"])),
    "admin": lambda s, u, d: admin_payload(s, u, d.get("q", "")),
    "admin_status": lambda s, u, d: s.admin_set_status(u, int(d["id"]), d["status"]),
    "admin_class_add": lambda s, u, d: s.create_class(u, int(d["gym_id"]), d["title"], d.get("instructor", ""),
                                                      _dt(d["start"].replace("T", " ")), int(d["capacity"])),
    "admin_class_delete": lambda s, u, d: s.delete_class(u, int(d["id"])),
    "admin_roster": lambda s, u, d: s.roster(u, int(d["id"])),
}


@app.post("/api/register")
def register():
    d = request.get_json(force=True, silent=True) or {}
    try:
        u = svc().register(d.get("name", ""), d.get("email", ""), d.get("password", ""),
                           int(d.get("plan_id", 1)), int(d.get("gym_id", 1)))
    except (GymError, ValueError) as e:
        return jsonify(error=str(e)), 400
    session["uid"] = u["id"]
    return jsonify(ok=True)


@app.post("/api/login")
def login():
    d = request.get_json(force=True, silent=True) or {}
    u = svc().login(d.get("email", ""), d.get("password", ""))
    if not u:
        return jsonify(error="Wrong email or password"), 401
    session["uid"] = u["id"]
    return jsonify(ok=True)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/options")
def options():
    s = svc()
    return jsonify(plans=s.plans(), gyms=s.gyms())


@app.post("/api/<action>")
def act(action):
    fn = ACTIONS.get(action)
    uid = session.get("uid")
    if not fn:
        return jsonify(error="Unknown action"), 404
    if not uid:
        return jsonify(error="Please sign in", auth=True), 401
    try:
        return jsonify(data=fn(svc(), uid, request.get_json(force=True, silent=True) or {}))
    except GymError as e:
        return jsonify(error=str(e)), 400
    except (KeyError, ValueError, TypeError):
        return jsonify(error="Please check the values you entered"), 400


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.errorhandler(Exception)
def _unexpected(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    app.logger.exception(e)
    return jsonify(error="Something went wrong"), 500


def init():
    s = GymService(connect(DB))
    s.seed_demo_classes(1)
    s.db.close()


init()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), threaded=True)
