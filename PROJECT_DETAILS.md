# Project Details

Supporting documentation for `week5Lab.ipynb`. Setup steps are in the [README](../README.md).

## 1. Design

- **One worker class per dataset** in `src/`. The notebook only calls methods, so every step is named, documented and reusable.
- **Shared database helpers** in `src/db.py` (`get_engine`, `read_sql`, `replace_rows`) read `DATABASE_URL` from `.env`.
- **Original data is never overwritten.** Raw tables in Neon are reloaded with `upload_sources()`; cleaned results go to separate `*_clean` tables, and comparison methods return copies.
- **Reproducible samples.** Public-data samples use a fixed `random_state=42`.

## 2. Data Sources

| Section | File | Description |
|---|---|---|
| 1 | `Pew Research Center Global Attitudes Spring 2025 Dataset CSV.csv` | 28,333 respondents, 24 countries, 483 variables |
| 1 | `Pew Research Center Global Attitudes Spring 2025 Metadata.xml` | DDI 2.5 codebook: question text and value labels |
| 1 | `README`, `Questionnaire`, `Topline` PDFs | Pew documentation (weights, question wording, results) |
| 2 | `billboard.csv` | 317 songs that entered the Billboard Top 100 in 1999–2000, one column per chart week |
| 3 | `cars.csv` | 406 cars (1970–1982), semicolon-separated, with a data-type label row |
| 3 | `vehicles.csv.zip` | US EPA fuel economy file; a sample of 1,000 petrol/diesel vehicles from 1984–1989 is used |
| 4 | `diabetes.csv` | Pima Indians Diabetes dataset, 768 women aged 21+ |
| 4 | `nhanes_2009_2012_raw.csv.zip` | US CDC NHANES 2009–2012 records; a sample of 1,000 women aged 21+ is used |

## 3. Database (Neon PostgreSQL)

Table definitions are in `sql/schema.sql`. The team role `tidying_cleaning_team` has read/write access.

| Table | Written by | Content |
|---|---|---|
| `cars_raw` | `CarsWorker.upload_sources()` | `cars.csv` as text, in file order |
| `cars_public_epa` | `CarsWorker.upload_sources()` | EPA sample |
| `cars_clean` | `CarsWorker.save_clean()` | Cleaned and imputed cars |
| `diabetes_raw` | `DiabetesWorker.upload_sources()` | `diabetes.csv` as supplied |
| `diabetes_public_nhanes` | `DiabetesWorker.upload_sources()` | NHANES sample |
| `diabetes_clean` | `DiabetesWorker.save_clean()` | Data after outlier treatment |

Sections 1 and 2 read their CSV files directly.

## 4. Worker Classes

### `PewWorker` (`src/pew_worker.py`)

| Method | Purpose |
|---|---|
| `load()` | Read the CSV; blank cells (question not asked) become `NaN` |
| `load_metadata()` | Parse value labels from the DDI codebook |
| `melt_income()` | Melt the 49 income columns into one long table; split names into `measure` and `country_name` |
| `add_metadata_columns()` | Add `country_label`, `income_label`, `response_status` |
| `summary()` | Valid answers per country and measure |

### `BillboardWorker` (`src/billboard_worker.py`)

| Method | Purpose |
|---|---|
| `load()` | Read the CSV |
| `melt_weeks()` | Melt week columns into `week` and `rank` |
| `clean_week_column()` | `"1st week"` → `1` |
| `drop_empty_ranks()` | Remove weeks when the song was not on the chart |
| `add_chart_date()` | Entry date + 7 days per week |
| `plot_rankings()` | Plotly ranking trajectories, rank 1 at the top |

### `CarsWorker` (`src/cars_worker.py`)

| Method | Purpose |
|---|---|
| `upload_sources()` | Load `cars.csv` and the EPA sample into Neon |
| `load()`, `drop_irrelevant_rows()` | Read `cars_raw`; remove the data-type label row |
| `zero_report()`, `convert_types()` | Count zeros; convert to numbers, impossible zeros → `NaN` |
| `merge_public_data()` | Translate the EPA sample to the lab schema and append it |
| `duplicates_report()`, `drop_duplicates()` | Find and remove exact duplicates |
| `drop_missing()`, `impute()` | Compare dropping vs simple imputation (on copies) |
| `center_stats()`, `distribution_plot()` | Mean, median, skew and histogram to choose a fill statistic |
| `group_impute()`, `regression_impute()`, `simple_impute()` | Imputation strategies |
| `compare_before_after()`, `before_after_plot()`, `save_clean()` | Evaluate and save the result |

### `DiabetesWorker` (`src/diabetes_worker.py`)

| Method | Purpose |
|---|---|
| `upload_sources()`, `load()` | Load `diabetes.csv` and the NHANES sample into Neon; read them back |
| `zero_report()`, `zeros_to_nan()` | Impossible zeros → `NaN` |
| `merge_public_data()`, `source_summary()` | Translate NHANES to the Pima schema and append it |
| `box_plot()`, `scatter_plot()` | Visual detection |
| `zscore_outliers()`, `iqr_bounds()`, `iqr_outliers()` | Statistical detection |
| `compare_methods()` | Z-score vs IQR counts per feature |
| `remove_outliers()`, `compare_before_after()`, `before_after_box()`, `save_clean()` | Treat, evaluate and save |

## 5. Key Decisions

| Section | Decision | Reason |
|---|---|---|
| 1 | Melt with `id`, `country`, `weight` only | Keeping all 434 other columns produced 1.4 million rows; other answers can be joined back on `id` |
| 1 | Non-responses read from the codebook labels | Codes differ by question (98/99 vs 8/9); a fixed list counted 3,085 non-responses as incomes |
| 2 | Drop empty weeks after melting | 74% of melted rows are weeks off the chart |
| 3 | Impute instead of drop | Dropping rows would remove 71% of the cars |
| 3 | Group median for `MPG`, regression for `Weight` and `Horsepower` | Uses related columns instead of stacking one value on ~950 EPA rows |
| 4 | Remove only diastolic pressure below 38 mm Hg | Physiologically implausible; high values and extreme BMI are real and kept |

## 6. Team and Workflow

Each member did a different job in each section, so everyone worked on all four datasets.

| Section | Class | Notebook | Markdown | Testing |
|---|---|---|---|---|
| 1 – PEW | John | Eche | Sultan | Antonio |
| 2 – Billboard | Eche | Antonio | John | Sultan |
| 3 – Cars | Antonio | Sultan | Eche | John |
| 4 – Diabetes | Sultan | John | Antonio | Eche |

| Role | Responsibility |
|---|---|
| Class | Write the dataset's worker class in `src/`, one method per step, with docstrings |
| Notebook | Call the class methods in the notebook (one call per cell) and complete the exercises |
| Markdown | Rewrite the section's explanations: goal, reasoning behind each step, key takeaways |
| Testing | Review the section's pull requests and run it from a fresh clone and virtual environment |

| Shared task | Owner |
|---|---|
| Repository setup and `.gitignore` | Sultan |
| `requirements.txt` | John |
| Replicability Check | Eche |
| Public repository and submission PDF | Antonio |

**Process**
1. All four classes were written in parallel, each on its own branch (`pew-class`, `billboard-class`, `cars-class`, `diabetes-class`).
2. Each class was merged through a pull request reviewed by that section's tester.
3. The notebook and markdown work was done one section at a time, so only one person edited the notebook at any moment.
4. After `requirements.txt` was added, each tester ran their section on their own laptop and sent their OS, Python version and any issues to the Replicability Check.

## 7. Replicability

- Dependencies were frozen with `pip freeze > requirements.txt` in the project virtual environment.
- The notebook was run end to end on a second machine in a new virtual environment created only from `requirements.txt`.
- Issues found and their fixes are documented in the **Replicability Check** at the end of the notebook.
