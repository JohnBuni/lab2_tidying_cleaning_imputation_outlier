# Week 5 Lab – Tidying, Cleaning, Imputation and Outliers

Data preprocessing on four datasets in one notebook, `week5Lab.ipynb`:

| Section | Dataset | Technique |
|---|---|---|
| 1 | PEW Research Center (Spring 2025) | Tidying with `melt`, labelling codes from survey metadata |
| 2 | Billboard Top 100 | Tidying with `melt` and string cleaning |
| 3 | Cars | Data cleaning, duplicates, dropping vs imputing missing values |
| 4 | Diabetes (Pima) | Outlier detection with box plots, scatter plots, Z-score and IQR |

## Requirements

- Python 3.12
- Access to the team's Neon PostgreSQL database (Sections 3 and 4)
- Database configuration provided to authorized team members by email, under the subject "PROG8245: Week 5 Lab – Team Contributions and Approach"

## How to Run

```bash
git clone https://github.com/JohnBuni/lab2_tidying_cleaning_imputation_outlier.git
cd lab2_tidying_cleaning_imputation_outlier

python -m venv .venv
.venv\Scripts\activate          # Windows
# .\.venv\Scripts\Activate.ps1  # Windows PowerShell (VS Code)
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

1. Copy `.env.example` to `.env` and paste the database connection string shared with the team.
2. Open `week5Lab.ipynb` from the project root and select the `.venv` kernel.
3. Run **Restart Kernel → Run All**.

## Project Structure

```
week5Lab.ipynb      Notebook (Sections 1–4)
src/                One worker class per dataset, plus shared database helpers
data/               Source datasets and Pew documentation
sql/schema.sql      Neon database tables
PROJECT_DETAILS.md               Project details
requirements.txt    Pinned dependencies
```

More detail on the datasets, database, worker classes and design decisions: [PROJECT_DETAILS.md](PROJECT_DETAILS.md).
