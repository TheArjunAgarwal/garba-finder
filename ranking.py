#!/usr/bin/env python3
"""Turn the Supabase `responses` CSV export into incomplete preference rankings.

Usage: python3 match_rankings.py responses.csv [--questions questions.json] [--out rankings]
Writes <out>.json (per-person ordered lists), <out>.csv (long format) and input.txt
(Haskell `read`-able [(String,[String])], best match first, for Irving's `roomies`).

Rules
 1. Hard filters (a pair is dropped if ANY fails, in either direction):
      - gender / "interested in" must match both ways
      - each person's age must be inside the other's age range
      - habits (smoking, alcohol, drugs) must not exceed the other's tolerance
 2. Everyone left is ranked by distance (smaller = better):
      (3 * meanAbsoluteDifferenceDist + pearsonDistance) // 4
 3. Pair questions: when A ranks B, A's *ideal-partner* answers are compared with
    B's *own* answers. "You only" questions compare A's own answers with B's own.
    So A's list of B and B's list of A can differ (A's wishes vs B's reality).
"""
import argparse, csv, json, math

INPUT_RANGE = 7
OUTPUT_RANGE = 100_000_000
PEARSON_RANGE = 100_000_000

HABIT = {"Never": 0, "Occasionally": 1, "Regularly": 2}            # partner's habit level
TOL_MAX = {"Fine": 2, "Okay occasionally": 1, "Dealbreaker": 0}   # highest habit level I accept
GENDER_TO_INTEREST = {"Man": "Men", "Woman": "Women", "Non-binary": "Non-binary people", "Other": "Other"}


def mean_abs_diff_dist(xs, ys):
    mean = sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs)
    return -round((INPUT_RANGE - mean) * (OUTPUT_RANGE / INPUT_RANGE))


def pearson(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    den = math.sqrt(sum(a * a for a in dx)) * math.sqrt(sum(b * b for b in dy))
    # Haskell would return NaN for a flat answer vector; treat it as "no correlation".
    return sum(a * b for a, b in zip(dx, dy)) / den if den else 0.0


def pearson_dist(xs, ys):
    r = PEARSON_RANGE // 2
    return -round(pearson(xs, ys) * r + r)


def distance(xs, ys):
    return (3 * mean_abs_diff_dist(xs, ys) + pearson_dist(xs, ys)) // 4   # // floors, like Haskell `div`


def load_people(path, questions):
    scored = [q for q in questions if q["type"] in ("dual", "scale")]
    habits = [q["id"] for q in questions if q["type"] == "dealbreaker"]
    people = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                d = row["data"]
                d = json.loads(d) if isinstance(d, str) else d
                you, ideal = [], []
                for q in scored:
                    a = d[q["id"]]
                    if q["type"] == "dual":
                        you.append(int(a["you"])); ideal.append(int(a["ideal"]))
                    else:
                        you.append(int(a)); ideal.append(int(a))
                people[row["email"].lower()] = {
                    "email": row["email"].lower(), "name": row.get("name", ""),
                    "gender": d["gender"], "into": set(d["interested_in"]), "age": int(d["age"]),
                    "amin": int(d["age_range"]["min"]), "amax": int(d["age_range"]["max"]),
                    "habits": {h: d[h] for h in habits}, "you": you, "ideal": ideal}
            except (KeyError, TypeError, ValueError) as e:
                print(f"skipping {row.get('email')}: incomplete/invalid answers ({e!r})")
    return people


def accepts(p, q):
    """Does q meet p's requirements?"""
    return (GENDER_TO_INTEREST.get(q["gender"]) in p["into"]
            and p["amin"] <= q["age"] <= p["amax"]
            and all(HABIT[q["habits"][h]["mine"]] <= TOL_MAX[p["habits"][h]["tol"]] for h in p["habits"]))


def hs_str(s):
    """Haskell string literal (what `show`/`read` use)."""
    out = []
    for ch in s:
        out.append("\\\\" if ch == "\\" else '\\"' if ch == '"' else ch if 32 <= ord(ch) < 127 else f"\\{ord(ch)}\\&")
    return '"' + "".join(out) + '"'


def to_haskell(ranks, keep_empty=False):
    items = [f"({hs_str(e)},[{','.join(hs_str(c) for _, c in r)}])" for e, r in ranks.items() if r or keep_empty]
    return "[" + ",\n ".join(items) + "]\n"


def rank_all(people):
    out = {}
    for p in people.values():
        cands = [(distance(p["ideal"], q["you"]), q["email"]) for q in people.values()
                 if q is not p and accepts(p, q) and accepts(q, p)]
        out[p["email"]] = sorted(cands)          # best (smallest distance) first, ties by email
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("--questions", default="questions.json"); ap.add_argument("--out", default="rankings")
    ap.add_argument("--haskell", default="input.txt"); ap.add_argument("--keep-empty", action="store_true")
    a = ap.parse_args()
    people = load_people(a.csv, json.load(open(a.questions))["questions"])
    ranks = rank_all(people)
    with open(a.out + ".json", "w") as f:
        json.dump({e: [{"email": c, "name": people[c]["name"], "distance": d} for d, c in r] for e, r in ranks.items()}, f, indent=1)
    with open(a.out + ".csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["person", "rank", "candidate", "distance"])
        for e, r in ranks.items():
            for i, (d, c) in enumerate(r, 1): w.writerow([e, i, c, d])
    with open(a.haskell, "w") as f: f.write(to_haskell(ranks, a.keep_empty))
    print(f"{len(people)} people; avg list length {sum(map(len, ranks.values()))/max(1,len(ranks)):.1f}; "
          f"{sum(1 for r in ranks.values() if not r)} with no acceptable match")