"""Turn the raw BC Ministry of Education CSVs in data/raw/ into the two compact
data files the dashboard loads (data/fsa.js and data/grad.js).

Run from the repo root after replacing any CSV in data/raw/:

    python scripts/build_data.py
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"

# The year range in each file name changes with every release, so the files are
# found by pattern. If several match, the last one alphabetically (newest) wins.
FSA_PATTERN = "*skills_assessment*.csv"
GRAD_RESULT_PATTERN = "graduation_assessment*proficiency_result.csv"
GRAD_PART_PATTERN = "graduation_assessment*participation_rate.csv"

# Schools with fewer writers than this are left out of the rankings. The
# ministry masks ("Msk") counts below 10 anyway, so this is the natural floor.
MIN_WRITERS = 10

# Why a school has a row in the source data but no rank.
MASKED, TOO_FEW, NO_WRITERS, ONE_SKILL = range(4)

ASSESSMENTS = ["Numeracy Assessment 10", "Literacy Assessment 10", "Literacy Assessment 12"]


def find(pattern):
    matches = sorted(RAW.glob(pattern))
    if not matches:
        raise SystemExit(f"No file matching {pattern} in {RAW}")
    print(f"reading {matches[-1].name}")
    return matches[-1]


def read_csv(path):
    # The ministry files are not consistently encoded: try UTF-8, fall back to cp1252.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(path, encoding=encoding, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"Cannot decode {path}")


def num(value):
    """Numeric value, or None for blanks and masked ("Msk") cells."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sector(row):
    return "I" if row["PUBLIC_OR_INDEPENDENT"].startswith("Independent") else "P"


class Schools:
    """Assigns each school a stable index and keeps its most recent name."""

    def __init__(self):
        self.index = {}
        self.rows = []
        self.name_year = []

    def add(self, row):
        number = row["SCHOOL_NUMBER"]
        i = self.index.get(number)
        if i is None:
            i = self.index[number] = len(self.rows)
            # The first three digits of a school number are the district it sits
            # in. Independent schools have no DISTRICT_NUMBER, so this is the
            # only way to place them geographically.
            self.rows.append([row["SCHOOL_NAME"].strip(), number[:3], sector(row), number])
            self.name_year.append(row["SCHOOL_YEAR"])
        elif row["SCHOOL_YEAR"] >= self.name_year[i]:
            self.rows[i][0] = row["SCHOOL_NAME"].strip()
            self.name_year[i] = row["SCHOOL_YEAR"]
        return i


def district_names(*tables):
    names = {}
    for rows in tables:
        for r in rows:
            if r["DISTRICT_NUMBER"] and r["DATA_LEVEL"] == "District Level":
                names[r["DISTRICT_NUMBER"]] = r["DISTRICT_NAME"].strip()
    return names


def pct(part, whole):
    return round(100 * part / whole, 1) if whole else None


def build_fsa(rows, districts):
    years = sorted({r["SCHOOL_YEAR"] for r in rows})
    schools = Schools()
    by_key = defaultdict(dict)
    province = {}

    for r in rows:
        if r["SUB_POPULATION"] != "All Students":
            continue
        if r["DATA_LEVEL"] == "Province Level" and r["PUBLIC_OR_INDEPENDENT"] == "Province-Total":
            key = f'{r["SCHOOL_YEAR"]}|{int(r["GRADE"])}'
            p = province.setdefault(key, {"w": 0, "ok": 0, "e": 0})
            p["w"] += num(r["NUMBER_WRITERS"]) or 0
            p["e"] += num(r["NUMBER_EXPECTED_WRITERS"]) or 0
            p["ok"] += (num(r["NUMBER_ONTRACK"]) or 0) + (num(r["NUMBER_EXTENDING"]) or 0)
        elif r["DATA_LEVEL"] == "School Level":
            by_key[(r["SCHOOL_NUMBER"], r["SCHOOL_YEAR"], int(r["GRADE"]))][r["FSA_SKILL_CODE"]] = r

    records = []
    excluded = []
    for (number, year, grade), skills in by_key.items():
        lit, numeracy = skills.get("Literacy"), skills.get("Numeracy")
        present = [r for r in (lit, numeracy) if r]
        medians = [num(r["MEDIAN_SCORE"]) for r in present]
        writers = [num(r["NUMBER_WRITERS"]) for r in present]
        expected = [num(r["NUMBER_EXPECTED_WRITERS"]) for r in present]
        reason = None
        if len(present) < 2:
            reason = ONE_SKILL
        elif None in medians or None in expected:
            reason = MASKED
        elif any(m <= 0 for m in medians):
            # A median of 0 is how the file records "nobody wrote", not a real score.
            reason = NO_WRITERS
        elif any(w is None or w < MIN_WRITERS for w in writers):
            reason = TOO_FEW
        if reason is not None:
            known = [int(e) for e in expected if e is not None]
            excluded.append([schools.add(present[0]), years.index(year), grade, reason,
                             max(known) if known else None])
            continue
        records.append([
            schools.add(lit),
            years.index(year),
            grade,
            round(medians[0], 1),
            round(medians[1], 1),
            pct(sum(writers), sum(expected)),
            round(num(lit["AVG_SCORE"]), 1),
            round(num(numeracy["AVG_SCORE"]), 1),
            int(writers[0]), int(expected[0]),
            int(writers[1]), int(expected[1]),
        ])

    return {
        "years": years,
        "districts": districts,
        "schools": schools.rows,
        # [school, year, grade, literacy median, numeracy median, participation %,
        #  literacy average, numeracy average, literacy writers, literacy expected,
        #  numeracy writers, numeracy expected]
        "records": records,
        # [school, year, grade, reason, expected writers]
        "excluded": excluded,
        "province": {k: {"proficient": pct(v["ok"], v["w"]), "participation": pct(v["w"], v["e"])}
                     for k, v in province.items()},
    }


LEVEL_COLUMNS = ["NUMBER_EMERGING", "NUMBER_DEVELOPING", "NUMBER_PROFICIENT", "NUMBER_EXTENDING"]


def ok_count(row):
    """Writers rated proficient or extending, or None if either count is masked."""
    proficient, extending = num(row["NUMBER_PROFICIENT"]), num(row["NUMBER_EXTENDING"])
    return proficient + extending if proficient is not None and extending is not None else None


def build_grad(result_rows, part_rows, districts):
    years = sorted({r["SCHOOL_YEAR"] for r in result_rows})
    schools = Schools()

    participation = {}
    for r in part_rows:
        if r["SUB_POPULATION"] == "All Students" and r["DATA_LEVEL"] == "School Level":
            rate, students = num(r["PARTICIPATION_RATE"]), num(r["NUMBER_STUDENT"])
            if rate is not None or students is not None:
                participation[(r["SCHOOL_NUMBER"], r["SCHOOL_YEAR"], r["GRADUATION_ASSESSMENT"])] = (
                    rate, int(students) if students is not None else None)

    # Numeracy is one test offered in two languages, so a school's English and
    # French rows are pooled. The French literacy rows are a different
    # assessment on a different score scale, so literacy uses English only.
    pooled = {}
    seen = {}
    province = {}
    for r in result_rows:
        if r["SUB_POPULATION"] != "All Students":
            continue
        assessment = r["GRADUATION_ASSESSMENT"]
        if r["ASSESSMENT_LANGUAGE"] == "French" and not assessment.startswith("Numeracy"):
            continue
        if r["DATA_LEVEL"] == "Province Level" and r["PUBLIC_OR_INDEPENDENT"] == "Province-Total":
            p = province.setdefault(f'{r["SCHOOL_YEAR"]}|{ASSESSMENTS.index(assessment)}',
                                    {"w": 0, "s": 0, "ok": 0})
            p["w"] += num(r["NUMBER_WRITERS"]) or 0
            p["s"] += num(r["SCORE"]) or 0
            p["ok"] += (num(r["NUMBER_PROFICIENT"]) or 0) + (num(r["NUMBER_EXTENDING"]) or 0)
        elif r["DATA_LEVEL"] == "School Level":
            seen[(r["SCHOOL_NUMBER"], r["SCHOOL_YEAR"], assessment)] = r
            writers, score = num(r["NUMBER_WRITERS"]), num(r["SCORE"])
            if writers is None or score is None:
                continue
            # Emerging, developing, proficient, extending. Any masked level
            # makes the whole breakdown unknown.
            levels = [num(r[c]) for c in LEVEL_COLUMNS]
            if None in levels:
                levels = None
            key = (r["SCHOOL_NUMBER"], r["SCHOOL_YEAR"], assessment)
            p = pooled.get(key)
            if p is None:
                pooled[key] = {"row": r, "w": writers, "s": score, "levels": levels,
                               "ok": ok_count(r)}
            else:
                p["w"] += writers
                p["s"] += score
                other = ok_count(r)
                p["ok"] = p["ok"] + other if p["ok"] is not None and other is not None else None
                p["levels"] = ([a + b for a, b in zip(p["levels"], levels)]
                               if p["levels"] and levels else None)

    records = []
    excluded = []
    for key, row in seen.items():
        p = pooled.get(key)
        if p is None or p["w"] < MIN_WRITERS:
            number, year, assessment = key
            excluded.append([schools.add(row), years.index(year), ASSESSMENTS.index(assessment),
                             MASKED if p is None else TOO_FEW,
                             participation.get(key, (None, None))[1]])
    for (number, year, assessment), p in pooled.items():
        if p["w"] < MIN_WRITERS:
            continue
        rate, students = participation.get((number, year, assessment), (None, None))
        records.append([
            schools.add(p["row"]),
            years.index(year),
            ASSESSMENTS.index(assessment),
            round(p["s"] / p["w"], 2),
            int(p["w"]),
            pct(p["ok"], p["w"]) if p["ok"] is not None else None,
            rate,
            [int(n) for n in p["levels"]] if p["levels"] else None,
            students,
        ])

    return {
        "years": years,
        "assessments": ASSESSMENTS,
        "districts": districts,
        "schools": schools.rows,
        # [school, year, assessment, mean score, writers, % proficient or extending,
        #  participation %, [emerging, developing, proficient, extending], students]
        "records": records,
        # [school, year, assessment, reason, students in the grade]
        "excluded": excluded,
        "province": {k: {"mean": round(v["s"] / v["w"], 2), "proficient": pct(v["ok"], v["w"])}
                     for k, v in province.items() if v["w"]},
    }


def write_js(name, variable, data):
    path = OUT / name
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    path.write_text(f"window.{variable}={payload};\n", encoding="utf-8")
    print(f"{path.relative_to(ROOT)}: {len(data['schools'])} schools, {len(data['records'])} ranked "
          f"results, {len(data['excluded'])} excluded, {path.stat().st_size / 1024:.0f} KB")


def main():
    fsa_rows = read_csv(find(FSA_PATTERN))
    result_rows = read_csv(find(GRAD_RESULT_PATTERN))
    part_rows = read_csv(find(GRAD_PART_PATTERN))
    districts = district_names(fsa_rows, result_rows, part_rows)
    write_js("fsa.js", "FSA_DATA", build_fsa(fsa_rows, districts))
    write_js("grad.js", "GRAD_DATA", build_grad(result_rows, part_rows, districts))


if __name__ == "__main__":
    main()
