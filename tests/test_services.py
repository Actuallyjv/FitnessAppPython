from datetime import date, datetime, timedelta

import pytest

from gymapp.db import connect
from gymapp.services import GymError, GymService

NOW = datetime(2026, 11, 3, 10, 0)  # a Tuesday


@pytest.fixture
def svc():
    s = GymService(connect(":memory:"))
    s.seed_demo_classes(1, NOW)
    return s


@pytest.fixture
def me(svc):
    return svc.register("Pat", "pat@example.com", "secret1", plan_id=1, home_gym_id=1, now=NOW)


def test_register_and_login(svc, me):
    assert me["member_code"].startswith("GYM") and len(me["member_code"]) == 10
    assert svc.login("PAT@example.com", "secret1")["id"] == me["id"]
    assert svc.login("pat@example.com", "wrong") is None
    with pytest.raises(GymError):
        svc.register("Pat", "pat@example.com", "secret1")
    with pytest.raises(GymError):
        svc.register("X", "bad-email", "secret1")
    with pytest.raises(GymError):
        svc.register("X", "x@y.com", "123")


def test_checkin_rules(svc, me):
    svc.checkin(me["id"], 1, NOW)
    with pytest.raises(GymError, match="hour"):
        svc.checkin(me["id"], 1, NOW + timedelta(minutes=10))
    with pytest.raises(GymError, match="home club"):
        svc.checkin(me["id"], 2, NOW + timedelta(hours=3))
    with pytest.raises(GymError, match="closed"):
        svc.checkin(me["id"], 1, NOW.replace(hour=3))
    svc.checkin(me["id"], 1, NOW + timedelta(hours=3))
    assert len(svc.checkin_history(me["id"])) == 2


def test_guest_pass_black_card_only(svc, me):
    with pytest.raises(GymError, match="guest"):
        svc.checkin(me["id"], 1, NOW, guest=True)
    svc.change_plan(me["id"], 2)
    svc.checkin(me["id"], 1, NOW, guest=True)
    assert svc.user(me["id"])["guest_passes"] == 0
    svc.checkin(me["id"], 2, NOW + timedelta(hours=2))  # Black Card: any club


def test_frozen_member_cannot_checkin(svc, me):
    svc.set_status(me["id"], "frozen")
    with pytest.raises(GymError, match="frozen"):
        svc.checkin(me["id"], 1, NOW)
    svc.set_status(me["id"], "active", NOW)
    svc.checkin(me["id"], 1, NOW)


def test_cancelled_only_reactivates(svc, me):
    svc.set_status(me["id"], "cancelled")
    with pytest.raises(GymError):
        svc.set_status(me["id"], "frozen")
    svc.set_status(me["id"], "active", NOW)


def test_streak(svc, me):
    for d in range(3):
        svc.checkin(me["id"], 1, NOW - timedelta(days=d))
    assert svc.streak(me["id"], NOW.date()) == 3
    assert svc.streak(me["id"], NOW.date() + timedelta(days=1)) == 3  # yesterday still counts
    assert svc.streak(me["id"], NOW.date() + timedelta(days=2)) == 0


def test_crowd(svc, me):
    assert svc.crowd(1, NOW)["label"] == "Not busy"
    svc.checkin(me["id"], 1, NOW)
    assert svc.crowd(1, NOW)["count"] == 1


def test_workout_flow_and_prs(svc, me):
    w = svc.start_workout(me["id"], NOW)
    bench = svc.exercises("Chest")[0]["id"]
    svc.add_set(me["id"], w, bench, 8, 60)
    svc.add_set(me["id"], w, bench, 5, 70)
    with pytest.raises(GymError):
        svc.add_set(me["id"], w, bench, 0, 10)
    svc.finish_workout(me["id"], w, NOW + timedelta(hours=1))
    with pytest.raises(GymError, match="finished"):
        svc.add_set(me["id"], w, bench, 5, 70)
    h = svc.workout_history(me["id"])[0]
    assert h["sets"] == 2 and h["volume"] == 8 * 60 + 5 * 70
    pr = svc.personal_records(me["id"])[0]
    assert pr["weight"] == 70 and pr["reps"] == 5


def test_cannot_touch_other_users_workout(svc, me):
    other = svc.register("Al", "al@example.com", "secret1", now=NOW)
    w = svc.start_workout(me["id"], NOW)
    with pytest.raises(GymError):
        svc.add_set(other["id"], w, 1, 5, 10)


def test_class_booking(svc, me):
    c = svc.classes(1, NOW)[0]
    svc.book_class(me["id"], c["id"], NOW)
    with pytest.raises(GymError, match="Already"):
        svc.book_class(me["id"], c["id"], NOW)
    assert len(svc.my_classes(me["id"], NOW)) == 1
    svc.cancel_class(me["id"], c["id"])
    assert svc.my_classes(me["id"], NOW) == []
    with pytest.raises(GymError, match="started"):
        svc.book_class(me["id"], c["id"], datetime.fromisoformat(c["start_ts"].replace(" ", "T")) + timedelta(minutes=1))


def test_class_capacity(svc, me):
    cid = svc.create_class(1, 1, "Tiny", "Z", NOW + timedelta(days=1), 1)
    svc.book_class(me["id"], cid, NOW)
    other = svc.register("Al", "al@example.com", "secret1", now=NOW)
    with pytest.raises(GymError, match="full"):
        svc.book_class(other["id"], cid, NOW)


def test_equipment_booking(svc, me):
    day = (NOW + timedelta(days=1)).date()
    eq = svc.equipment(1)[0]["id"]
    slots = svc.equipment_slots(eq, day, NOW)
    assert slots[0] == datetime(2026, 11, 4, 5, 0)
    svc.book_equipment(me["id"], eq, slots[0], NOW)
    assert slots[0] not in svc.equipment_slots(eq, day, NOW)
    with pytest.raises(GymError, match="per day"):
        svc.book_equipment(me["id"], eq, slots[3], NOW)  # Classic: 1 per day
    other = svc.register("Al", "al@example.com", "secret1", now=NOW)
    with pytest.raises(GymError, match="unavailable"):
        svc.book_equipment(other["id"], eq, slots[0], NOW)
    with pytest.raises(GymError, match="future"):
        svc.book_equipment(other["id"], eq, NOW - timedelta(hours=1), NOW)


def test_massage_chair_black_card_only(svc, me):
    chair = [e for e in svc.equipment(1) if e["kind"] == "Recovery"][0]["id"]
    slot = svc.equipment_slots(chair, (NOW + timedelta(days=1)).date(), NOW)[0]
    with pytest.raises(GymError, match="Black Card"):
        svc.book_equipment(me["id"], chair, slot, NOW)
    svc.change_plan(me["id"], 2)
    svc.book_equipment(me["id"], chair, slot, NOW)


def test_challenge_and_badge(svc, me):
    svc.join_challenge(me["id"], 1, NOW - timedelta(days=6))
    for d in range(5):
        new = svc.checkin(me["id"], 1, NOW - timedelta(days=4 - d))
    assert new == ["Consistency Starter"]
    assert [b["badge"] for b in svc.badges(me["id"])] == ["Consistency Starter"]
    assert svc.checkin(me["id"], 1, NOW + timedelta(days=1)) == []  # not re-awarded


def test_leaderboard(svc, me):
    svc.checkin(me["id"], 1, NOW)
    lb = svc.leaderboard(30, NOW)
    assert lb[0]["name"] == "Pat" and lb[0]["visits"] == 1


def test_plans_and_today(svc, me):
    assert svc.todays_session(me["id"]) is None
    svc.activate_plan(me["id"], 2, NOW)
    monday = date(2026, 11, 2)
    assert svc.todays_session(me["id"], monday)["title"] == "Push"
    assert svc.todays_session(me["id"], date(2026, 11, 3))["title"] == "Rest day"


def test_nutrition(svc, me):
    svc.log_food(me["id"], "Egg", 78, 6, NOW.date())
    lid = svc.log_food(me["id"], "Banana", 105, 1.3, NOW.date())
    d = svc.nutrition_day(me["id"], NOW.date())
    assert d["calories"] == 183 and d["remaining"] == 2200 - 183
    svc.delete_food(me["id"], lid)
    assert svc.nutrition_day(me["id"], NOW.date())["calories"] == 78
    with pytest.raises(GymError):
        svc.log_food(me["id"], "", 10)
    svc.update_profile(me["id"], calorie_goal=2000)
    with pytest.raises(GymError):
        svc.update_profile(me["id"], calorie_goal=100)


def test_weight_log_overwrites_same_day(svc, me):
    svc.log_weight(me["id"], 80, NOW.date())
    svc.log_weight(me["id"], 79.5, NOW.date())
    assert svc.weight_history(me["id"]) == [{"day": "2026-11-03", "kg": 79.5}]
    with pytest.raises(GymError):
        svc.log_weight(me["id"], 5)


def test_admin_permissions_and_stats(svc, me):
    for fn in (lambda: svc.admin_stats(me["id"]), lambda: svc.list_members(me["id"]),
               lambda: svc.create_class(me["id"], 1, "x", "y", NOW, 5)):
        with pytest.raises(GymError, match="Admin"):
            fn()
    svc.checkin(me["id"], 1, NOW)
    st = svc.admin_stats(1, NOW)
    assert st["members"] == 1 and st["checkins_today"] == 1 and st["monthly_revenue"] == 15.0
    assert svc.list_members(1, "pat")[0]["name"] == "Pat"
    svc.admin_set_status(1, me["id"], "frozen")
    assert svc.user(me["id"])["status"] == "frozen"
    cid = svc.classes(1, NOW)[0]["id"]
    svc.book_class(me["id"] if False else svc.register("B", "b@b.com", "secret1", now=NOW)["id"], cid, NOW)
    assert len(svc.roster(1, cid)) == 1
    svc.delete_class(1, cid)
    assert svc.roster(1, cid) == []


def test_nearest_gyms(svc):
    assert svc.nearest_gyms(40.7831, -73.9712)[0]["name"] == "Uptown"
