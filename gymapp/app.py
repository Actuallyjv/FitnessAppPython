"""Kivy UI for the gym app."""
from datetime import date, datetime, timedelta

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.togglebutton import ToggleButton

from .db import connect
from .services import FMT, GymError, GymService
from .widgets import (BG, GREEN, PURPLE, RED, YELLOW, Barcode, Card, bar, button, field, form, label,
                      message, scroll_column, spinner)

TABS = ["Home", "Train", "Book", "Gyms", "More"]


class Root(BoxLayout):
    def __init__(self, svc, **kw):
        super().__init__(orientation="vertical", **kw)
        self.svc = svc
        self.user_id = None
        self.tab = "Home"
        self.sub = {"Train": "Workout", "More": "Membership"}
        self.workout_id = None
        self.book_gym = None
        self.show_login()

    # ----- plumbing -----
    def act(self, fn, *a, ok=None, **kw):
        """Run a service call; show rule violations as a popup. Returns (success, result)."""
        try:
            res = fn(*a, **kw)
        except GymError as e:
            message("Heads up", str(e))
            return False, None
        if ok:
            message("Done", ok(res) if callable(ok) else ok)
        self.refresh()
        return True, res

    @property
    def me(self):
        return self.svc.user(self.user_id)

    def clear(self):
        self.clear_widgets()

    # ----- auth -----
    def show_login(self, register=False):
        self.user_id = None
        self.clear()
        sv, col = scroll_column()
        col.add_widget(label("GYM APP", 34, YELLOW, bold=True, halign="center"))
        col.add_widget(label("Judgement-free fitness", 15, halign="center"))
        card = Card("Create account" if register else "Sign in")
        name = field("Full name")
        email = field("Email")
        pw = field("Password (6+ characters)", password=True)
        plan = spinner([f"{p['name']} - ${p['price']:.2f}/mo" for p in self.svc.plans()])
        gym = spinner([g["name"] for g in self.svc.gyms()])
        if register:
            for w in (name, email, pw, plan, gym):
                card.add_widget(w)
        else:
            card.add_widget(email)
            card.add_widget(pw)

        def go():
            if register:
                plans = self.svc.plans()
                ok, u = self.act_login(self.svc.register, name.text, email.text, pw.text,
                                       plans[plan.values.index(plan.text)]["id"],
                                       [g for g in self.svc.gyms() if g["name"] == gym.text][0]["id"])
            else:
                u = self.svc.login(email.text, pw.text)
                if not u:
                    message("Sign in failed", "Wrong email or password")
                    return
            if u:
                self.user_id = u["id"]
                self.show_main()

        card.add_widget(button("Create account" if register else "Sign in", go))
        card.add_widget(button("Have an account? Sign in" if register else "New here? Join now",
                               lambda: self.show_login(not register), color=(0.3, 0.3, 0.38, 1)))
        if not register:
            card.add_widget(label("Demo admin: admin@gym.local / admin123", 12, (0.7, 0.7, 0.7, 1)))
        col.add_widget(card)
        self.add_widget(sv)

    def act_login(self, fn, *a):
        try:
            return True, fn(*a)
        except GymError as e:
            message("Heads up", str(e))
            return False, None

    # ----- shell -----
    def show_main(self):
        self.clear()
        self.content = BoxLayout()
        self.add_widget(self.content)
        nav = BoxLayout(size_hint_y=None, height=dp(52))
        for t in TABS:
            tb = ToggleButton(text=t, group="nav", state="down" if t == self.tab else "normal",
                              background_normal="", background_down="",
                              background_color=PURPLE if t == self.tab else (0.2, 0.2, 0.25, 1))
            tb.bind(on_release=lambda b, t=t: self.go(t))
            nav.add_widget(tb)
        self.add_widget(nav)
        self.refresh()

    def go(self, tab):
        self.tab = tab
        self.show_main()

    def refresh(self):
        if self.user_id is None or not hasattr(self, "content") or not self.content.get_root_window():
            return
        self.content.clear_widgets()
        sv, col = scroll_column()
        getattr(self, "page_" + self.tab.lower())(col)
        self.content.add_widget(sv)

    def segmented(self, col, tab, options):
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        for o in options:
            b = button(o, lambda o=o: self.set_sub(tab, o), color=PURPLE if self.sub[tab] == o else (0.3, 0.3, 0.38, 1), height=40)
            row.add_widget(b)
        col.add_widget(row)

    def set_sub(self, tab, o):
        self.sub[tab] = o
        self.refresh()

    # ----- Home -----
    def page_home(self, col):
        s, u = self.svc, self.me
        plan = [p for p in s.plans() if p["id"] == u["plan_id"]][0]
        col.add_widget(label(f"Hi, {u['name'].split()[0]}!", 26, bold=True))
        if u["status"] != "active":
            col.add_widget(label(f"[b]Membership {u['status']}[/b] - manage it in More", 14, RED))
        card = Card(f"{plan['name']} member")
        card.add_widget(Barcode(u["member_code"]))
        card.add_widget(label(u["member_code"], 18, halign="center", bold=True))
        col.add_widget(card)

        gyms = s.gyms()
        c = Card("Check in")
        home = [g for g in gyms if g["id"] == u["home_gym_id"]][0]
        sp = spinner([g["name"] for g in gyms], home["name"])
        c.add_widget(sp)
        gid = lambda: [g for g in gyms if g["name"] == sp.text][0]["id"]
        def do(guest=False):
            ok, new = self.act(s.checkin, self.user_id, gid(), guest=guest)
            if ok:
                message("Checked in", "Have a great workout!" + (f"\nBadge earned: {', '.join(new)}" if new else ""))
        c.row(button("Check in", do, GREEN), button("Use guest pass (%d)" % u["guest_passes"], lambda: do(True),
                                                    (0.3, 0.3, 0.38, 1)))
        col.add_widget(c)

        st = Card("Your stats")
        st.add_widget(label(f"Current streak: [b]{s.streak(self.user_id)}[/b] day(s)", 16))
        badges = s.badges(self.user_id)
        st.add_widget(label("Badges: " + (", ".join(b["badge"] for b in badges) or "none yet - join a challenge in More"), 14))
        col.add_widget(st)

        t = s.todays_session(self.user_id)
        c = Card("Today's session")
        if t:
            c.add_widget(label(f"{t['plan']}: [b]{t['title']}[/b]", 15))
            for e in t["exercises"]:
                c.add_widget(label("  - " + e, 14))
        else:
            c.add_widget(label("No plan active. Pick one under Train > Plans.", 14))
        col.add_widget(c)

        c = Card("Recent visits")
        for h in s.checkin_history(self.user_id, 5) or []:
            c.add_widget(label(f"{h['ts']}  {h['gym']}" + ("  (guest)" if h["guest"] else ""), 14))
        if not s.checkin_history(self.user_id, 1):
            c.add_widget(label("No visits yet", 14))
        col.add_widget(c)

    # ----- Train -----
    def page_train(self, col):
        self.segmented(col, "Train", ["Workout", "Plans", "Nutrition", "Progress"])
        getattr(self, "train_" + self.sub["Train"].lower())(col)

    def train_workout(self, col):
        s = self.svc
        c = Card("Log workout")
        if self.workout_id is None:
            c.add_widget(button("Start workout", self.start_workout, GREEN))
        else:
            ex = s.exercises()
            sp = spinner([f"{e['name']} ({e['muscle']})" for e in ex])
            reps = field("Reps", input_filter="int")
            wt = field("Weight (kg)", input_filter="float")
            c.add_widget(sp)
            c.row(reps, wt)

            def add():
                try:
                    r, w = int(reps.text), float(wt.text or 0)
                except ValueError:
                    return message("Heads up", "Enter reps and weight as numbers")
                self.act(s.add_set, self.user_id, self.workout_id, ex[sp.values.index(sp.text)]["id"], r, w)

            c.add_widget(button("Add set", add))
            for i, st in enumerate(s.workout_sets(self.workout_id), 1):
                c.add_widget(label(f"{i}. {st['exercise']}: {st['reps']} x {st['weight']:g} kg", 14))
            c.add_widget(button("Finish workout", self.finish_workout, RED))
        col.add_widget(c)
        c = Card("History")
        for w in s.workout_history(self.user_id, 8):
            c.add_widget(label(f"{w['started']}  {w['sets']} sets, {w['volume']:,.0f} kg volume", 14))
        if not s.workout_history(self.user_id, 1):
            c.add_widget(label("No workouts yet", 14))
        col.add_widget(c)

    def start_workout(self):
        ok, wid = self.act(self.svc.start_workout, self.user_id)
        if ok:
            self.workout_id = wid
            self.refresh()

    def finish_workout(self):
        ok, new = self.act(self.svc.finish_workout, self.user_id, self.workout_id)
        if ok:
            self.workout_id = None
            message("Nice work!", "Workout saved." + (f"\nBadge earned: {', '.join(new)}" if new else ""))
            self.refresh()

    def train_plans(self, col):
        s = self.svc
        active = s.active_plan(self.user_id)
        for p in s.workout_plans():
            c = Card(p["name"] + ("  [active]" if active and active["id"] == p["id"] else ""))
            c.add_widget(label(f"{p['goal']} - {p['description']}", 13))
            for d in s.plan_schedule(p["id"]):
                c.add_widget(label(f"[b]{'Mon Tue Wed Thu Fri Sat Sun'.split()[d['day']]}[/b] {d['title']}: "
                                   + ", ".join(d["exercises"]), 13))
            c.add_widget(button("Use this plan", lambda pid=p["id"]: self.act(s.activate_plan, self.user_id, pid)))
            col.add_widget(c)

    def train_nutrition(self, col):
        s = self.svc
        d = s.nutrition_day(self.user_id)
        c = Card("Today")
        c.add_widget(label(f"[b]{d['calories']}[/b] / {d['goal']} kcal   -   {d['protein']:.0f} g protein", 16))
        c.add_widget(bar(d["calories"], d["goal"]))
        c.add_widget(label(f"{d['remaining']} kcal remaining" if d["remaining"] >= 0 else f"{-d['remaining']} kcal over", 13,
                           GREEN if d["remaining"] >= 0 else RED))
        for i in d["items"]:
            c.row(label(f"{i['name']} - {i['calories']} kcal", 14),
                  button("x", lambda iid=i["id"]: self.act(s.delete_food, self.user_id, iid), RED, 36, size_hint_x=0.2), height=36)
        col.add_widget(c)
        foods = s.foods()
        c = Card("Quick add")
        sp = spinner([f"{f['name']} ({f['calories']} kcal)" for f in foods])
        c.add_widget(sp)
        def quick():
            f = foods[sp.values.index(sp.text)]
            self.act(s.log_food, self.user_id, f["name"], f["calories"], f["protein"])
        c.add_widget(button("Add", quick))
        c.add_widget(button("Custom food...", self.custom_food, (0.3, 0.3, 0.38, 1)))
        c.add_widget(button("Set calorie goal...", self.set_goal, (0.3, 0.3, 0.38, 1)))
        col.add_widget(c)

    def custom_food(self):
        def sub(v):
            try:
                self.act(self.svc.log_food, self.user_id, v["n"], int(v["c"]), float(v["p"] or 0))
            except ValueError:
                message("Heads up", "Calories and protein must be numbers")
        form("Custom food", [("n", "Name", {}), ("c", "Calories", {"input_filter": "int"}),
                             ("p", "Protein (g)", {"input_filter": "float"})], sub, "Add")

    def set_goal(self):
        def sub(v):
            try:
                ok, _ = self.act(self.svc.update_profile, self.user_id, calorie_goal=int(v["g"]))
                return ok
            except ValueError:
                message("Heads up", "Enter a number")
                return False
        form("Daily calorie goal", [("g", "kcal", {"input_filter": "int", "text": str(self.me["calorie_goal"])})], sub)

    def train_progress(self, col):
        s = self.svc
        c = Card("Body weight")
        w = field("Today's weight (kg)", input_filter="float")
        c.row(w, button("Log", lambda: self.log_weight(w.text), height=42, size_hint_x=0.4))
        hist = s.weight_history(self.user_id, 10)
        for h in hist:
            c.add_widget(label(f"{h['day']}: {h['kg']:g} kg", 14))
        if len(hist) > 1:
            diff = hist[0]["kg"] - hist[-1]["kg"]
            c.add_widget(label(f"Change over {len(hist)} entries: [b]{diff:+.1f} kg[/b]", 14))
        col.add_widget(c)
        c = Card("Personal records")
        prs = s.personal_records(self.user_id)
        for p in prs:
            c.add_widget(label(f"{p['exercise']}: {p['weight']:g} kg x {p['reps']}", 14))
        if not prs:
            c.add_widget(label("Log some sets to see your PRs", 14))
        col.add_widget(c)

    def log_weight(self, text):
        try:
            self.act(self.svc.log_weight, self.user_id, float(text))
        except ValueError:
            message("Heads up", "Enter your weight as a number")

    # ----- Book -----
    def page_book(self, col):
        s = self.svc
        gyms = s.gyms()
        if self.book_gym is None:
            self.book_gym = self.me["home_gym_id"]
        cur = [g for g in gyms if g["id"] == self.book_gym][0]
        sp = spinner([g["name"] for g in gyms], cur["name"])
        sp.bind(text=lambda i, t: self.change_book_gym([g for g in gyms if g["name"] == t][0]["id"]))
        col.add_widget(sp)

        c = Card("Your bookings")
        mine = s.my_classes(self.user_id)
        eq = s.my_equipment(self.user_id)
        for m in mine:
            c.row(label(f"{m['start_ts']}  {m['title']} @ {m['gym']}", 13),
                  button("Cancel", lambda cid=m["id"]: self.act(s.cancel_class, self.user_id, cid), RED, 36, size_hint_x=0.3), height=40)
        for m in eq:
            c.row(label(f"{m['start_ts']}  {m['name']} @ {m['gym']}", 13),
                  button("Cancel", lambda bid=m["id"]: self.act(s.cancel_equipment, self.user_id, bid), RED, 36, size_hint_x=0.3), height=40)
        if not mine and not eq:
            c.add_widget(label("Nothing booked", 14))
        col.add_widget(c)

        c = Card("Classes - next 7 days")
        booked = {m["id"] for m in mine}
        for k in s.classes(self.book_gym):
            full = k["booked"] >= k["capacity"]
            txt = f"[b]{k['title']}[/b] with {k['instructor']}\n{k['start_ts']} - {k['booked']}/{k['capacity']} spots"
            if k["id"] in booked:
                c.add_widget(label(txt + "  [color=33cc66]booked[/color]", 13))
            else:
                c.row(label(txt, 13), button("Full" if full else "Book", lambda cid=k["id"]: self.act(s.book_class, self.user_id, cid, ok="Class booked!"),
                                             (0.3, 0.3, 0.38, 1) if full else GREEN, 36, size_hint_x=0.3), height=52)
        col.add_widget(c)

        c = Card("Reserve equipment (30 min)")
        items = s.equipment(self.book_gym)
        esp = spinner([e["name"] for e in items])
        days = [date.today() + timedelta(days=i) for i in range(4)]
        dsp = spinner([d.strftime("%a %b %d") for d in days])
        c.add_widget(esp)
        c.add_widget(dsp)
        slots_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        slots_box.bind(minimum_height=slots_box.setter("height"))
        c.add_widget(slots_box)

        def show_slots(*_):
            slots_box.clear_widgets()
            eid = items[esp.values.index(esp.text)]["id"]
            slots = s.equipment_slots(eid, days[dsp.values.index(dsp.text)])
            if not slots:
                slots_box.add_widget(label("No open slots", 13))
            for i in range(0, min(len(slots), 12), 3):
                r = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(4))
                for sl in slots[i:i + 3]:
                    r.add_widget(button(sl.strftime("%H:%M"), lambda sl=sl, eid=eid: self.act(
                        s.book_equipment, self.user_id, eid, sl, ok="Reserved!"), height=38))
                slots_box.add_widget(r)
            if len(slots) > 12:
                slots_box.add_widget(label(f"+{len(slots) - 12} later slots - pick another day to see more", 12))

        esp.bind(text=show_slots)
        dsp.bind(text=show_slots)
        show_slots()
        col.add_widget(c)

    def change_book_gym(self, gid):
        if gid != self.book_gym:
            self.book_gym = gid
            self.refresh()

    # ----- Gyms -----
    def page_gyms(self, col):
        s = self.svc
        now = datetime.now()
        col.add_widget(label("Clubs", 24, bold=True))
        for g in s.gyms():
            open_ = s.is_open(g["id"], now)
            cr = s.crowd(g["id"], now)
            h = s.hours(g["id"], now.weekday())
            c = Card(g["name"] + ("  (home)" if g["id"] == self.me["home_gym_id"] else ""))
            c.add_widget(label(g["address"], 13))
            hours = "Open 24 hours" if h[0] == "00:00" and h[1] == "24:00" else f"{h[0]} - {h[1]}"
            c.add_widget(label(("[color=33cc66]Open now[/color]" if open_ else "[color=dd4444]Closed[/color]") + f"  -  {hours}", 14))
            c.add_widget(label(f"Crowd: {cr['label']} ({cr['count']} recent check-ins)", 13))
            c.add_widget(bar(cr["percent"]))
            if g["id"] != self.me["home_gym_id"]:
                c.add_widget(button("Make home club", lambda gid=g["id"]: self.act(s.update_profile, self.user_id, home_gym_id=gid), height=38))
            col.add_widget(c)

    # ----- More -----
    def page_more(self, col):
        opts = ["Membership", "Challenges"] + (["Admin"] if self.me["role"] == "admin" else [])
        if self.sub["More"] not in opts:
            self.sub["More"] = opts[0]
        self.segmented(col, "More", opts)
        getattr(self, "more_" + self.sub["More"].lower())(col)

    def more_membership(self, col):
        s, u = self.svc, self.me
        plans = s.plans()
        cur = [p for p in plans if p["id"] == u["plan_id"]][0]
        c = Card("Membership")
        c.add_widget(label(f"{u['name']}  -  {u['email']}", 14))
        c.add_widget(label(f"Plan: [b]{cur['name']}[/b] (${cur['price']:.2f}/mo)\nStatus: [b]{u['status']}[/b]\nNext billing: {u['next_billing']}\nGuest passes: {u['guest_passes']}", 14))
        if u["status"] == "active":
            c.add_widget(button("Freeze membership", lambda: self.act(s.set_status, self.user_id, "frozen"), (0.3, 0.3, 0.38, 1)))
            c.add_widget(button("Cancel membership", self.confirm_cancel, RED))
        else:
            c.add_widget(button("Reactivate", lambda: self.act(s.set_status, self.user_id, "active"), GREEN))
        col.add_widget(c)
        for p in plans:
            c = Card(p["name"] + ("  [current]" if p["id"] == u["plan_id"] else ""))
            c.add_widget(label(f"${p['price']:.2f}/mo - {p['perks']}", 13))
            if p["id"] != u["plan_id"] and u["status"] == "active":
                c.add_widget(button(f"Switch to {p['name']}", lambda pid=p["id"]: self.act(s.change_plan, self.user_id, pid, ok="Plan updated"), height=38))
            col.add_widget(c)
        col.add_widget(button("Sign out", self.show_login, (0.3, 0.3, 0.38, 1)))

    def confirm_cancel(self):
        from .widgets import popup
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        box.add_widget(label("Cancel your membership? You can reactivate later.", 15))
        p = popup("Are you sure?", box, 0.35)
        box.add_widget(button("Yes, cancel", lambda: (p.dismiss(), self.act(self.svc.set_status, self.user_id, "cancelled")), RED))
        box.add_widget(button("Keep membership", p.dismiss))

    def more_challenges(self, col):
        s = self.svc
        for ch in s.challenges(self.user_id):
            c = Card(ch["title"])
            c.add_widget(label(f"{ch['target']} {ch['metric']} in {ch['days']} days - badge: {ch['badge']}", 13))
            if ch["joined"]:
                c.add_widget(label(f"{ch['progress']}/{ch['target']}" + ("  - expired" if ch.get("expired") else ""), 14))
                c.add_widget(bar(ch["progress"], ch["target"]))
            else:
                c.add_widget(button("Join", lambda cid=ch["id"]: self.act(s.join_challenge, self.user_id, cid), GREEN, 38))
            col.add_widget(c)
        c = Card("Leaderboard - visits, last 30 days")
        lb = s.leaderboard()
        for i, r in enumerate(lb, 1):
            c.add_widget(label(f"{i}. {r['name']} - {r['visits']}", 14))
        if not lb:
            c.add_widget(label("No check-ins yet", 14))
        col.add_widget(c)

    def more_admin(self, col):
        s, a = self.svc, self.user_id
        st = s.admin_stats(a)
        c = Card("Dashboard")
        c.add_widget(label(f"Members: {st['members']} ({st['active']} active)\nCheck-ins today: {st['checkins_today']}\n"
                           f"Monthly revenue: ${st['monthly_revenue']:.2f}\n" +
                           "  ".join(f"{p['name']}: {p['n']}" for p in st["by_plan"]), 14))
        col.add_widget(c)
        c = Card("Members")
        q = field("Search name, email or code")
        c.add_widget(q)
        res = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        res.bind(minimum_height=res.setter("height"))
        c.add_widget(res)

        def search(*_):
            res.clear_widgets()
            for m in s.list_members(a, q.text)[:8]:
                nxt = "active" if m["status"] != "active" else "frozen"
                r = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
                r.add_widget(label(f"{m['name']} ({m['plan']})\n{m['member_code']} - {m['status']}", 12))
                r.add_widget(button("Freeze" if nxt == "frozen" else "Activate",
                                    lambda mid=m["id"], n=nxt: self.act(s.admin_set_status, a, mid, n), (0.3, 0.3, 0.38, 1), 36, size_hint_x=0.3))
                res.add_widget(r)
        q.bind(text=search)
        search()
        col.add_widget(c)
        c = Card("Classes")
        c.add_widget(button("Add class...", self.add_class, GREEN, 38))
        for k in s.all_classes(a)[:10]:
            c.row(label(f"{k['start_ts']} {k['title']} @ {k['gym']} ({k['booked']}/{k['capacity']})", 12),
                  button("Roster", lambda cid=k["id"], t=k["title"]: self.show_roster(cid, t), height=34, size_hint_x=0.25),
                  button("Del", lambda cid=k["id"]: self.act(s.delete_class, a, cid), RED, 34, size_hint_x=0.18), height=44)
        col.add_widget(c)
        c = Card("Recent check-ins")
        for r in s.recent_checkins(a, 8):
            c.add_widget(label(f"{r['ts']}  {r['name']} @ {r['gym']}", 12))
        col.add_widget(c)

    def show_roster(self, cid, title):
        r = self.svc.roster(self.user_id, cid)
        message(title, "\n".join(f"{m['name']} ({m['member_code']})" for m in r) or "No bookings yet")

    def add_class(self):
        gyms = self.svc.gyms()
        def sub(v):
            try:
                start = datetime.strptime(v["start"], FMT)
                gid = [g for g in gyms if g["name"].lower() == v["gym"].strip().lower()][0]["id"]
                ok, _ = self.act(self.svc.create_class, self.user_id, gid, v["title"], v["inst"], start, int(v["cap"]))
                return ok
            except (ValueError, IndexError):
                message("Heads up", "Check the gym name, start (YYYY-MM-DD HH:MM) and capacity")
                return False
        form("New class", [("title", "Title", {}), ("inst", "Instructor", {}),
                           ("gym", "Gym (" + ", ".join(g["name"] for g in gyms) + ")", {}),
                           ("start", "Start: YYYY-MM-DD HH:MM", {}), ("cap", "Capacity", {"input_filter": "int"})], sub, "Create")


class GymApp(App):
    title = "Gym App"

    def __init__(self, db_path="gymapp.db", **kw):
        super().__init__(**kw)
        self.db_path = db_path

    def build(self):
        Window.clearcolor = BG
        svc = GymService(connect(self.db_path))
        svc.seed_demo_classes(1)
        return Root(svc)


def main():
    GymApp().run()
