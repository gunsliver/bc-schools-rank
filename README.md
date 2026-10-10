# bc-schools-rank

A mobile-friendly dashboard ranking British Columbia schools from the public
BC Ministry of Education and Child Care assessment data. It is a static page,
so it can be hosted on GitHub Pages as is.

- **Elementary** — Foundation Skills Assessment (Grades 4 and 7), 2021/22 to 2025/26
- **Secondary** — Graduation Assessments (Numeracy 10, Literacy 10, Literacy 12), 2017/18 to 2024/25

This is an unofficial family project, not an official ranking.

## Where the data comes from

All three files are published on the [BC Data Catalogue](https://catalogue.data.gov.bc.ca/)
by the Education Analytics Office of the BC Ministry of Education and Child Care.
Each dataset page also carries the licence, field-definition PDFs and a
"Working with the extract" guide.

| File in `data/raw/` | Dataset page | Resource to download (CSV) |
| --- | --- | --- |
| `foundation_skills_assessment_2021-22_to_2025-26.csv` | [BC Schools - Foundation Skills Assessment (FSA)](https://catalogue.data.gov.bc.ca/dataset/bc-schools-foundation-skills-assessment-fsa-) | "Foundation Skills Assessment 2021/22 to 2025/26 Residents only" |
| `graduation_assessment_2017-18_to_2024-25_proficiency_result.csv` | [Graduation Assessments](https://catalogue.data.gov.bc.ca/dataset/graduation-assessments) | "Graduation Assessments 2017/18 to 2024/25 Proficiency Result" |
| `graduation_assessment_2017-18_to_2024-25_participation_rate.csv` | [Graduation Assessments](https://catalogue.data.gov.bc.ca/dataset/graduation-assessments) | "Graduation Assessments 2017/18 to 2024/25 Participation Result" |

The Ministry republishes each file in full once a year with the newest school
year added, and the year range in the file name moves forward. Counts below 10
are masked as `Msk` in every file.

### Columns the dashboard uses

Every file starts with the same identifying columns: `SCHOOL_YEAR`,
`DATA_LEVEL` (Province / District / School), `PUBLIC_OR_INDEPENDENT`,
`DISTRICT_NUMBER`, `DISTRICT_NAME`, `SCHOOL_NUMBER`, `SCHOOL_NAME` and
`SUB_POPULATION`. Only `All Students` rows are used.

| File | Other columns used | Used for |
| --- | --- | --- |
| FSA (19 columns) | `GRADE`, `FSA_SKILL_CODE`, `NUMBER_EXPECTED_WRITERS`, `NUMBER_WRITERS`, `NUMBER_ONTRACK`, `NUMBER_EXTENDING`, `AVG_SCORE`, `MEDIAN_SCORE` | Index, participation, the BC "on track or extending" figure |
| Graduation proficiency (16 columns) | `GRADUATION_ASSESSMENT`, `ASSESSMENT_LANGUAGE`, `NUMBER_WRITERS`, `NUMBER_EMERGING`, `NUMBER_DEVELOPING`, `NUMBER_PROFICIENT`, `NUMBER_EXTENDING`, `SCORE` | Mean score (`SCORE` ÷ `NUMBER_WRITERS`), proficiency levels |
| Graduation participation (13 columns) | `GRADUATION_ASSESSMENT`, `NUMBER_STUDENT`, `PARTICIPATION_RATE` | Participation rate |

## Yearly update

1. Open the two dataset pages above and download the newest CSV for each of
   the three resources.
2. Put them in `data/raw/` and delete the older file each one replaces. The
   names can stay as downloaded: the build script finds the files by pattern
   (`*skills_assessment*.csv`, `graduation_assessment*proficiency_result.csv`,
   `graduation_assessment*participation_rate.csv`).
3. Rebuild the data the page loads:

   ```bash
   python scripts/build_data.py
   ```

4. Preview locally (below) and check that the new school year appears in the
   "School year" dropdown on both tabs and that the top schools look sensible.
5. Commit the new CSVs together with the regenerated `data/fsa.js` and
   `data/grad.js`, and push. GitHub Pages republishes on its own.

If the script stops with a `KeyError`, the Ministry has renamed a column:
compare the CSV header with the column list above and update
`scripts/build_data.py`.

## Layout

| Path | What it is |
| --- | --- |
| `index.html` | The whole dashboard (no build step, no external libraries) |
| `data/raw/*.csv` | The CSVs as downloaded from the BC Data Catalogue |
| `data/fsa.js`, `data/grad.js` | Compact data the page loads, generated from the CSVs |
| `scripts/build_data.py` | Regenerates the two `.js` files from `data/raw/` |

## Previewing locally

```bash
python -m http.server 8765
```

Then open http://localhost:8765.

The calculation rules are described in the "How these numbers are calculated"
section at the bottom of the page.
