"""Worker class for Section 4 - Outlier Detection (Diabetes Dataset)."""

import numpy as np
import pandas as pd
import plotly.express as px

from src.db import get_engine, read_sql, replace_rows

# Columns of the Pima diabetes file, in file order.
SCHEMA = ["Pregnancies", "Glucose", "BloodPressure", "SkinThickness", "Insulin",
          "BMI", "DiabetesPedigreeFunction", "Age", "Outcome"]
# Physiological measurements where 0 is impossible and means "not measured".
ZERO_MEANS_MISSING = ["Glucose", "BloodPressure", "SkinThickness", "Insulin", "BMI"]
# NHANES columns kept in Neon (original NHANES names).
NHANES_COLUMNS = ["ID", "SurveyYr", "Gender", "Age", "Race1", "BMI",
                  "BPDiaAve", "nPregnancies", "Diabetes"]


class DiabetesWorker:
    """Finds and treats outliers in the Pima diabetes data, extended with NHANES public records."""

    def __init__(self, engine=None):
        """Connect to the team Neon database (engine from .env unless one is passed)."""
        self.engine = engine if engine is not None else get_engine()
        self.df = None
        self.baseline = None  # snapshot before any outlier removal
        self.public = None    # translated NHANES records
        self.clean = None     # cleaned copy (the original self.df is never overwritten)

    # ------------------------------------------------------- one-time upload
    def upload_sources(self, pima_csv: str = "data/diabetes.csv",
                       nhanes_file: str = "data/nhanes_2009_2012_raw.csv.zip",
                       n: int = 1000, random_state: int = 42) -> pd.DataFrame:
        """Upload diabetes.csv and a fixed NHANES sample to Neon; re-running replaces them."""
        raw = pd.read_csv(pima_csv)
        raw.columns = [c.lower() for c in raw.columns]
        raw.insert(0, "row_num", range(1, len(raw) + 1))

        nhanes = pd.read_csv(nhanes_file, low_memory=False)
        # Same population as Pima (women aged 21+) with the fields the lab needs.
        keep = ((nhanes["Gender"] == "female") & (nhanes["Age"] >= 21)
                & nhanes[["BMI", "BPDiaAve", "Diabetes"]].notna().all(axis=1))
        sample = nhanes.loc[keep, NHANES_COLUMNS].sample(n=n, random_state=random_state)
        sample.columns = [c.lower() for c in sample.columns]

        rows = {"diabetes_raw": replace_rows(self.engine, "diabetes_raw", raw),
                "diabetes_public_nhanes": replace_rows(self.engine, "diabetes_public_nhanes", sample)}
        return pd.DataFrame.from_dict(rows, orient="index", columns=["rows_uploaded"])

    # ------------------------------------------------------------------ 4.1
    def load(self) -> pd.DataFrame:
        """Read diabetes_raw from Neon in original file order."""
        raw = read_sql(self.engine, "SELECT * FROM diabetes_raw ORDER BY row_num")
        self.df = raw.drop(columns="row_num")
        self.df.columns = SCHEMA
        self.baseline = self.df.copy()
        return self.df

    def zero_report(self) -> pd.DataFrame:
        """Count and percentage of zero values per column."""
        zeros = (self.df[SCHEMA] == 0).sum()
        return pd.DataFrame({"zeros": zeros, "zeros_%": (zeros / len(self.df) * 100).round(2)})

    def zeros_to_nan(self, columns=ZERO_MEANS_MISSING) -> pd.DataFrame:
        """Replace impossible zeros (e.g. BMI = 0) with NaN so they are not analysed as real values."""
        for col in columns:
            self.df[col] = self.df[col].mask(self.df[col] == 0)
        self.baseline = self.df.copy()
        return self.df

    def missing_report(self) -> pd.DataFrame:
        """Missing count, missing percentage and valid count per column."""
        missing = self.df.isna().sum()
        return pd.DataFrame({"missing": missing,
                             "missing_%": (missing / len(self.df) * 100).round(2),
                             "valid": self.df.notna().sum()})

    # ------------------------------------------------- verbal change: merge
    def merge_public_data(self) -> pd.DataFrame:
        """Read the NHANES sample from Neon, translate it to the Pima schema and append it."""
        s = read_sql(self.engine, "SELECT * FROM diabetes_public_nhanes ORDER BY id")
        public = pd.DataFrame({
            "Pregnancies": s["npregnancies"],             # times pregnant
            "Glucose": np.nan,                            # not in NHANES
            "BloodPressure": s["bpdiaave"].mask(s["bpdiaave"] == 0),  # diastolic mm Hg; 0 = not measured
            "SkinThickness": np.nan,                      # not in NHANES
            "Insulin": np.nan,                            # not in NHANES
            "BMI": s["bmi"],
            "DiabetesPedigreeFunction": np.nan,           # not in NHANES
            "Age": s["age"],
            "Outcome": (s["diabetes"] == "Yes").astype(int),  # told by a doctor they have diabetes
        })
        public["source"] = "nhanes_public"
        self.public = public.reset_index(drop=True)
        self.df = pd.concat([self.df.assign(source="pima_original"), self.public],
                            ignore_index=True)
        self.baseline = self.df.copy()
        return self.df

    def source_summary(self) -> pd.DataFrame:
        """Rows, mean age, mean BMI and diabetes rate for each data source."""
        return self.df.groupby("source").agg(
            rows=("Age", "size"), mean_age=("Age", "mean"), mean_bmi=("BMI", "mean"),
            diabetes_rate=("Outcome", "mean")).round(3)

    # ------------------------------------------------------------------ 4.2
    def box_plot(self, columns):
        """Plotly box plot of one or several columns (points beyond the whiskers are shown)."""
        columns = [columns] if isinstance(columns, str) else list(columns)
        long = self.df[columns + ["source"]].melt(id_vars="source", var_name="feature",
                                                  value_name="value").dropna()
        fig = px.box(long, x="feature", y="value", points="outliers",
                     title="Box plots: " + ", ".join(columns),
                     labels={"feature": "Feature", "value": "Value"})
        return fig

    # ------------------------------------------------------------------ 4.3
    def scatter_plot(self, x: str, y: str):
        """Plotly scatter plot of two features, coloured by data source."""
        fig = px.scatter(self.df.dropna(subset=[x, y]), x=x, y=y, color="source", opacity=0.6,
                         title=f"{y} vs {x}", labels={x: x, y: y, "source": "Source"})
        return fig

    # ------------------------------------------------------------------ 4.4
    def zscore_outliers(self, column: str, threshold: float = 3) -> pd.DataFrame:
        """Rows whose |z| = |x - mean| / std is above the threshold (NaN ignored)."""
        s = self.df[column]
        z = (s - s.mean()) / s.std(ddof=0)
        flagged = self.df.loc[z.abs() > threshold].copy()
        flagged["z_score"] = z[z.abs() > threshold].round(2)
        return flagged

    # ------------------------------------------------------------------ 4.5
    def iqr_bounds(self, column: str, factor: float = 1.5) -> pd.Series:
        """Q1, Q3, IQR and the lower/upper fences Q1 - factor*IQR and Q3 + factor*IQR."""
        q1, q3 = self.df[column].quantile([0.25, 0.75])
        iqr = q3 - q1
        return pd.Series({"Q1": q1, "Q3": q3, "IQR": iqr,
                          "lower": q1 - factor * iqr, "upper": q3 + factor * iqr}).round(3)

    def iqr_outliers(self, column: str, factor: float = 1.5, side: str = "both") -> pd.DataFrame:
        """Rows outside the IQR fences of one column (side: 'both', 'lower' or 'upper')."""
        b = self.iqr_bounds(column, factor)
        s = self.df[column]
        low, high = s < b["lower"], s > b["upper"]
        mask = {"both": low | high, "lower": low, "upper": high}[side]
        return self.df.loc[mask]

    # ------------------------------------------------------------------ 4.6
    def compare_methods(self, columns, threshold: float = 3, factor: float = 1.5) -> pd.DataFrame:
        """Outlier counts per column by Z-score and IQR, and how many rows both methods flag."""
        rows = []
        for col in columns:
            z_idx = set(self.zscore_outliers(col, threshold).index)
            i_idx = set(self.iqr_outliers(col, factor).index)
            rows.append({"feature": col, "valid_values": int(self.df[col].notna().sum()),
                         "zscore_outliers": len(z_idx), "iqr_outliers": len(i_idx),
                         "flagged_by_both": len(z_idx & i_idx),
                         "skewness": round(self.df[col].skew(), 2)})
        return pd.DataFrame(rows).set_index("feature")

    # ------------------------------------------------------------------ 4.7
    def remove_outliers(self, columns, method: str = "iqr", threshold: float = 3,
                        factor: float = 1.5, side: str = "both") -> pd.DataFrame:
        """Build a cleaned COPY without the rows flagged in the given columns (original kept)."""
        columns = [columns] if isinstance(columns, str) else list(columns)
        drop = set()
        for col in columns:
            if method == "iqr":
                drop |= set(self.iqr_outliers(col, factor, side).index)
            elif method == "zscore":
                drop |= set(self.zscore_outliers(col, threshold).index)
            else:
                raise ValueError("method must be 'iqr' or 'zscore'")
        self.clean = self.df.drop(index=sorted(drop)).copy()
        return self.clean

    def compare_before_after(self, columns) -> pd.DataFrame:
        """Rows, mean, median and standard deviation before and after outlier removal."""
        out = {}
        for label, data in (("before", self.df), ("after", self.clean)):
            stats = {"rows": len(data)}
            for col in columns:
                stats[f"{col}_mean"] = round(data[col].mean(), 2)
                stats[f"{col}_median"] = round(data[col].median(), 2)
                stats[f"{col}_std"] = round(data[col].std(), 2)
            out[label] = stats
        return pd.DataFrame(out)

    def before_after_box(self, column: str):
        """Box plots of one column before and after outlier removal."""
        both = pd.concat([pd.DataFrame({column: self.df[column], "stage": "before"}),
                          pd.DataFrame({column: self.clean[column], "stage": "after"})]).dropna()
        fig = px.box(both, x="stage", y=column, color="stage", points="outliers",
                     title=f"{column} before vs after outlier removal",
                     labels={"stage": "Stage", column: column})
        return fig.update_layout(showlegend=False)

    def save_clean(self) -> pd.DataFrame:
        """Write the cleaned copy to the diabetes_clean table in Neon."""
        out = self.clean[SCHEMA + ["source"]].copy()
        out.columns = [c.lower() for c in out.columns]
        rows = replace_rows(self.engine, "diabetes_clean", out)
        return pd.DataFrame({"table": ["diabetes_clean"], "rows_written": [rows]})
