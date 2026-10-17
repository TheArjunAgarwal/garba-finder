#!/usr/bin/env python3
"""Build an explorable SQLite database + HTML report from the Supabase CSV export.

Usage: python3 build_db.py responses.csv [--questions questions.json] [--db prom.db] [--report report.html]
Needs: pandas, matplotlib  (pip install pandas matplotlib)
Needs match_rankings.py in the same folder (reuses its filters and distance metric).

Then explore with:  sqlite3 prom.db   |  DB Browser for SQLite  |  pip install datasette && datasette prom.db
"""
import argparse, base64, csv, io, json, math, os, sqlite3, textwrap
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import ranking as mr

YOU, IDEAL = "#e0a06b", "#7fb0ff"

SCHEMA = """
CREATE TABLE questions(qid TEXT PRIMARY KEY, theme TEXT, theme_name TEXT, kind TEXT, text TEXT,
                      low_label TEXT, high_label TEXT, ideal_low_label TEXT, ideal_high_label TEXT, you_caption TEXT, ideal_caption TEXT);
CREATE TABLE people(email TEXT PRIMARY KEY, name TEXT, gender TEXT, age INT, age_min INT, age_max INT, created_at TEXT);
CREATE TABLE interests(email TEXT, interested_in TEXT);
CREATE TABLE habits(email TEXT, habit TEXT, mine TEXT, tolerance TEXT);
CREATE TABLE answers(email TEXT, qid TEXT, theme TEXT, kind TEXT, you INT, ideal INT);  -- ideal is NULL for 'you only' questions
-- one row per ordered pair: how `a` sees `b`
CREATE TABLE pairs(a TEXT, b TEXT, a_rejects_b TEXT, b_rejects_a TEXT, compatible INT, dist INT, rank_in_a_list INT,
                   PRIMARY KEY(a, b));
CREATE VIEW mutual AS  -- compatible pairs (a<b) with both directions' distance and rank
  SELECT x.a, x.b, x.dist AS dist_a_view, y.dist AS dist_b_view, x.rank_in_a_list AS rank_a_view, y.rank_in_a_list AS rank_b_view
  FROM pairs x JOIN pairs y ON x.a = y.b AND x.b = y.a WHERE x.compatible = 1 AND x.a < x.b;
CREATE VIEW answers_text AS  -- answers with the question wording, handy for SQL
  SELECT a.email, a.qid, q.theme_name, q.text, q.low_label, q.high_label, a.you, a.ideal FROM answers a JOIN questions q USING(qid);
CREATE VIEW question_stats AS
  SELECT qid, kind, COUNT(*) n, ROUND(AVG(you),2) mean_you, ROUND(AVG(ideal),2) mean_ideal, ROUND(AVG(ideal-you),2) mean_gap FROM answers GROUP BY qid;
"""


def rejection_reasons(p, q):
    """Why p would not accept q (same rules as match_rankings.accepts)."""
    r = []
    if mr.GENDER_TO_INTEREST.get(q["gender"]) not in p["into"]: r.append("gender")
    if not p["amin"] <= q["age"] <= p["amax"]: r.append("age")
    r += [h for h in p["habits"] if mr.HABIT[q["habits"][h]["mine"]] > mr.TOL_MAX[p["habits"][h]["tol"]]]
    return r


def build_db(people, qs, created, path):
    if os.path.exists(path): os.remove(path)
    con = sqlite3.connect(path); con.executescript(SCHEMA)
    themes = {t["id"]: t["name"] for t in json.load(open(ARGS.questions))["themes"]}
    scored = [q for q in qs if q["type"] in ("dual", "scale")]
    con.executemany("INSERT INTO questions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    [(q["id"], q["theme"], themes[q["theme"]], q["type"], q["text"], q["lo"], q["hi"], q.get("ilo", q["lo"]) if q["type"] == "dual" else None,
                      q.get("ihi", q["hi"]) if q["type"] == "dual" else None, q.get("yc"), q.get("ic")) for q in scored])
    for p in people.values():
        con.execute("INSERT INTO people VALUES(?,?,?,?,?,?,?)",
                    (p["email"], p["name"], p["gender"], p["age"], p["amin"], p["amax"], created.get(p["email"], "")))
        con.executemany("INSERT INTO interests VALUES(?,?)", [(p["email"], i) for i in sorted(p["into"])])
        con.executemany("INSERT INTO habits VALUES(?,?,?,?)", [(p["email"], h, v["mine"], v["tol"]) for h, v in p["habits"].items()])
        con.executemany("INSERT INTO answers VALUES(?,?,?,?,?,?)",
                        [(p["email"], q["id"], q["theme"], q["type"], p["you"][i], p["ideal"][i] if q["type"] == "dual" else None)
                         for i, q in enumerate(scored)])
    rows = []
    for p in people.values():
        mine = []
        for q in people.values():
            if q is p: continue
            ra, rb = rejection_reasons(p, q), rejection_reasons(q, p)
            ok = not ra and not rb
            d = mr.distance(p["ideal"], q["you"])
            row = [p["email"], q["email"], ",".join(ra), ",".join(rb), int(ok), d, None]
            rows.append(row)
            if ok: mine.append((d, q["email"], row))
        for rk, (_, _, row) in enumerate(sorted(mine, key=lambda t: t[:2]), 1): row[6] = rk
    con.executemany("INSERT INTO pairs VALUES(?,?,?,?,?,?,?)", rows)
    con.commit(); return con


# ---------------------------------------------------------------- report
def short(t, n=60): return textwrap.shorten(t, n, placeholder="…")


def png(fig):
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=110, bbox_inches="tight"); plt.close(fig)
    return f'<img src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


def report(con, path):
    q = lambda sql: pd.read_sql(sql, con)
    ppl, ans, pairs = q("SELECT * FROM people"), q("SELECT * FROM answers"), q("SELECT * FROM pairs")
    qinfo = q("SELECT * FROM questions"); sections = []
    def add(title, html): sections.append(f"<h2>{title}</h2>{html}")
    def safe(title, fn):
        try: add(title, fn())
        except Exception as e: add(title, f"<p class=n>(skipped: {e})</p>")

    comp = pairs[pairs.compatible == 1]
    pool = comp.groupby("a").size().reindex(ppl.email, fill_value=0)
    add("Overview", q("""SELECT COUNT(*) AS people, MIN(age) AS min_age, ROUND(AVG(age),1) AS mean_age, MAX(age) AS max_age FROM people""").to_html(index=False)
        + pd.DataFrame({"metric": ["compatible pairs (unordered)", "mean acceptable partners / person", "people with 0 acceptable partners"],
                        "value": [len(comp) // 2, round(pool.mean(), 1) if len(pool) else 0, int((pool == 0).sum())]}).to_html(index=False))

    def demo():
        fig, ax = plt.subplots(1, 4, figsize=(15, 3))
        ppl.age.plot.hist(bins=range(15, 40), ax=ax[0], color=YOU); ax[0].set_title("Age")
        ppl.gender.value_counts().plot.bar(ax=ax[1], color=YOU, rot=0); ax[1].set_title("Gender")
        q("SELECT interested_in, COUNT(*) c FROM interests GROUP BY 1").set_index("interested_in").c.plot.bar(ax=ax[2], color=IDEAL, rot=20); ax[2].set_title("Interested in")
        pd.to_datetime(ppl.created_at, errors="coerce").dt.date.value_counts().sort_index().plot(ax=ax[3], marker="o", color=YOU); ax[3].set_title("Signups per day")
        return png(fig)
    safe("Who filled it in", demo)

    def habits():
        h = q("SELECT * FROM habits"); fig, ax = plt.subplots(1, 3, figsize=(14, 3))
        for a, (name, g) in zip(ax, h.groupby("habit")):
            pd.DataFrame({"habit": g.mine.value_counts(), "tolerance of partner's": g.tolerance.value_counts()}).fillna(0).plot.bar(ax=a, rot=15, color=[YOU, IDEAL]); a.set_title(name)
        return png(fig)
    safe("Habits and tolerances", habits)

    def grids():
        out = ""
        for th, g in qinfo.groupby("theme", sort=True):
            qs_ = list(g.itertuples()); rows = math.ceil(len(qs_) / 4)
            fig, axs = plt.subplots(rows, 4, figsize=(14, 3.0 * rows), squeeze=False)
            for a in axs.flat: a.axis("off")
            for a, qi in zip(axs.flat, qs_):
                a.axis("on"); d = ans[ans.qid == qi.qid]; xs = range(1, 8)
                cy = d.you.value_counts().reindex(xs, fill_value=0)
                if qi.kind == "dual":
                    ci = d.ideal.value_counts().reindex(xs, fill_value=0)
                    a.bar([x - .2 for x in xs], cy, .4, color=YOU, label="you"); a.bar([x + .2 for x in xs], ci, .4, color=IDEAL, label="ideal")
                    a.legend(fontsize=6)
                else: a.bar(xs, cy, .8, color=YOU)
                a.set_title(qi.qid + (" (pair): " if qi.kind == "dual" else ": ") + "\n".join(textwrap.wrap(short(qi.text, 70), 38)), fontsize=7); a.set_xticks(list(xs))
            fig.suptitle(g.theme_name.iloc[0], y=1.03); fig.tight_layout()
            st = q(f"SELECT qid, text AS question, low_label AS \"1 =\", high_label AS \"7 =\", mean_you, mean_ideal FROM questions JOIN question_stats USING(qid) WHERE theme='{th}'")
            out += png(fig) + st.to_html(index=False, na_rep="")
        return out
    safe("Answer distributions (amber = you, blue = ideal partner)", grids)

    def gap():
        d = q("SELECT qid, text, ideal_caption, mean_you, mean_ideal, mean_gap FROM questions JOIN question_stats USING(qid) WHERE questions.kind='dual'").set_index("qid")
        fig, ax = plt.subplots(figsize=(8, 4)); d.mean_gap.rename(lambda k: f"{k}: {short(d.text[k], 45)}").plot.barh(ax=ax, color=IDEAL)
        ax.axvline(0, color="#888"); ax.set_xlabel("mean(ideal - you): what people want more/less of than they give"); return png(fig) + d.to_html()
    safe("Pair questions: do people want more than they give?", gap)

    def corr():
        c = ans.pivot(index="email", columns="qid", values="you").corr()
        fig, ax = plt.subplots(figsize=(11, 9)); im = ax.imshow(c, cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(c))); ax.set_xticklabels(c.columns, rotation=90, fontsize=6); ax.set_yticks(range(len(c))); ax.set_yticklabels(c.index, fontsize=6)
        fig.colorbar(im, shrink=.6); return png(fig) + qinfo[["qid", "text"]].to_html(index=False)
    safe("Which questions move together (correlation of 'you' answers)", corr)

    def matching():
        fig, ax = plt.subplots(1, 3, figsize=(15, 3.2))
        pool.plot.hist(bins=max(5, min(20, len(pool))), ax=ax[0], color=YOU); ax[0].set_title("Acceptable partners per person")
        why = {"gender": 0, "age": 0, "smoking": 0, "alcohol": 0, "drugs": 0}
        for r in pairs.a_rejects_b[pairs.a_rejects_b != ""]:
            for k in r.split(","): why[k] += 1
        pd.Series(why).plot.bar(ax=ax[1], color=IDEAL, rot=0); ax[1].set_title("Times a person rejected someone, by reason")
        comp.dist.plot.hist(bins=30, ax=ax[2], color=YOU); ax[2].set_title("Distance, compatible pairs (lower = closer)")
        return png(fig)
    safe("Matching pool", matching)

    def pop():
        d = comp.groupby("b").agg(listed_by=("a", "size"), mean_rank=("rank_in_a_list", "mean"), top3=("rank_in_a_list", lambda s: (s <= 3).sum()))
        d = d.join(ppl.set_index("email")[["name"]]).sort_values(["top3", "listed_by"], ascending=False).round(2)
        return "<p class=n>Popularity = how often others rank this person; mean_rank closer to 1 is better.</p>" + d.head(15).to_html()
    safe("Most wanted people", pop)

    html = f"""<!doctype html><meta charset=utf-8><title>Garba Finder report</title>
<style>body{{font:15px system-ui;max-width:1100px;margin:30px auto;padding:0 16px}}img{{max-width:100%;display:block;margin:8px 0}}
table{{border-collapse:collapse;margin:8px 0}}td,th{{border:1px solid #ccc;padding:3px 8px;text-align:right}}.n{{color:#777}}</style>
<h1>Garba Finder: data report</h1>{''.join(sections)}"""
    open(path, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("--questions", default="questions.json")
    ap.add_argument("--db", default="prom.db"); ap.add_argument("--report", default="report.html")
    ARGS = ap.parse_args()
    qs = json.load(open(ARGS.questions))["questions"]
    people = mr.load_people(ARGS.csv, qs)
    created = {r["email"].lower(): r.get("created_at", "") for r in csv.DictReader(open(ARGS.csv, newline="", encoding="utf-8"))}
    con = build_db(people, qs, created, ARGS.db)
    report(con, ARGS.report)
    print(f"{len(people)} people -> {ARGS.db} (tables: people, interests, habits, answers, questions, pairs; views: mutual, question_stats) and {ARGS.report}")