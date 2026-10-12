"""Worker class for Section 3 - Data Cleaning (Cars Dataset)."""

import numpy as np
import pandas as pd
import plotly.express as px
from sklearn.impute import SimpleImputer

from src.db import get_engine, read_sql, replace_rows

# Columns of the lab's Cars schema, in file order.
SCHEMA = ["Car", "MPG", "Cylinders", "Displacement", "Horsepower",
          "Weight", "Acceleration", "Model", "Origin"]
NUMERIC = ["MPG", "Cylinders", "Displacement", "Horsepower",
           "Weight", "Acceleration", "Model"]
# Type labels that appear in the second line of the raw file.
TYPE_LABELS = {"STRING", "DOUBLE", "INT", "CAT"}
# Cubic inches in one litre (the lab measures Displacement in cubic inches).
LITRES_TO_CUBIC_INCHES = 61.0237

# Brand -> region, matching the three Origin values of the lab file.
MAKE_ORIGIN = {
    "US": ["AM General", "American Motors Corporation", "Avanti Motor Corporation",
           "Buick", "Cadillac", "Chevrolet", "Chrysler", "Dodge", "Eagle", "Ford",
           "GMC", "General Motors", "Geo", "Jeep", "Lincoln", "Mercury",
           "Oldsmobile", "Plymouth", "Pontiac", "Saleen"],
    "Europe": ["Alfa Romeo", "Aston Martin", "Audi", "BMW", "Bertone", "Dacia",
               "Ferrari", "Jaguar", "Lamborghini", "Land Rover", "Lotus",
               "Maserati", "Mercedes-Benz", "Merkur", "Peugeot", "Pininfarina",
               "Porsche", "Renault", "Rolls-Royce", "Saab", "Sterling",
               "Volkswagen", "Volvo", "Yugo"],
    "Japan": ["Acura", "Daihatsu", "Honda", "Isuzu", "Mazda", "Mitsubishi",
              "Nissan", "Subaru", "Suzuki", "Toyota"],
}
ORIGIN_OF = {make: region for region, makes in MAKE_ORIGIN.items() for make in makes}


class CarsWorker:
    """Cleans the Cars dataset: junk rows, data types, public-data merge, duplicates and missing values."""

    def __init__(self, engine=None):
        """Connect to the team Neon database (engine from .env unless one is passed)."""
        self.engine = engine if engine is not None else get_engine()
        self.df = None
        self.baseline = None  # snapshot of the data before any imputation
        self.public = None    # translated public records, kept for inspection
        self.imputer = None   # fitted SimpleImputer

    # ------------------------------------------------------- one-time upload
    def upload_sources(self, cars_csv: str = "data/cars.csv",
                       epa_file: str = "data/vehicles.csv.zip", n: int = 1000,
                       years=(1984, 1989), random_state: int = 42) -> pd.DataFrame:
        """Upload cars.csv (as text) and a fixed EPA sample to Neon; run once, re-running replaces them."""
        raw = pd.read_csv(cars_csv, sep=";", dtype=str, keep_default_na=False, na_values=[""])
        raw.columns = [c.strip().lower() for c in raw.columns]
        raw.insert(0, "row_num", range(1, len(raw) + 1))

        epa = pd.read_csv(epa_file, low_memory=False)
        # Conventional gasoline/diesel vehicles from the years closest to the lab data,
        # from brands that map to the lab's three Origin values.
        keep = (
            (epa["atvType"].isna() | (epa["atvType"] == "Diesel"))
            & epa["fuelType1"].isin(["Regular Gasoline", "Premium Gasoline", "Diesel"])
            & epa["year"].between(*years)
            & epa["make"].isin(ORIGIN_OF.keys())
        )
        sample = epa.loc[keep].sample(n=n, random_state=random_state)
        sample = sample[["id", "make", "model", "year", "comb08", "cylinders",
                         "displ", "fuelType1", "atvType", "trany", "VClass"]]
        sample.columns = ["epa_id", "make", "model", "year", "comb08", "cylinders",
                          "displ", "fueltype1", "atvtype", "trany", "vclass"]

        rows = {"cars_raw": replace_rows(self.engine, "cars_raw", raw),
                "cars_public_epa": replace_rows(self.engine, "cars_public_epa", sample)}
        return pd.DataFrame.from_dict(rows, orient="index", columns=["rows_uploaded"])

    # ------------------------------------------------------------------ 3.1
    def load(self) -> pd.DataFrame:
        """Read cars_raw from Neon in original file order, every value as text."""
        raw = read_sql(self.engine, "SELECT * FROM cars_raw ORDER BY row_num")
        self.df = raw.drop(columns="row_num")
        self.df.columns = SCHEMA
        return self.df

    def drop_irrelevant_rows(self) -> pd.DataFrame:
        """Remove rows that hold data-type labels (e.g. STRING;DOUBLE;...) instead of a car."""
        is_label_row = self.df.apply(
            lambda row: row.dropna().str.strip().str.upper().isin(TYPE_LABELS).all(),
            axis=1,
        )
        self.df = self.df.loc[~is_label_row].reset_index(drop=True)
        return self.df

    # ------------------------------------------------------------------ 3.2
    def convert_types(self, zero_means_missing=("MPG", "Horsepower")) -> pd.DataFrame:
        """Convert numeric columns to numbers and turn impossible zeros into NaN."""
        for col in NUMERIC:
            self.df[col] = pd.to_numeric(self.df[col], errors="coerce")
        for col in zero_means_missing:
            self.df.loc[self.df[col] == 0, col] = np.nan
        self.df["Car"] = self.df["Car"].str.strip()
        self.df["Origin"] = self.df["Origin"].str.strip().astype("category")
        self.baseline = self.df.copy()
        return self.df

    def zero_report(self) -> pd.Series:
        """Count zero values per numeric column (run before convert_types)."""
        values = self.df[NUMERIC].apply(pd.to_numeric, errors="coerce")
        return (values == 0).sum()

    def missing_report(self) -> pd.DataFrame:
        """Missing count, missing percentage and valid (notna) count per column."""
        missing = self.df.isna().sum()
        return pd.DataFrame({
            "missing": missing,
            "missing_%": (missing / len(self.df) * 100).round(2),
            "valid": self.df.notna().sum(),
        })

    # ------------------------------------------------- verbal change: merge
    def merge_public_data(self) -> pd.DataFrame:
        """Read the EPA sample from Neon, translate it to the lab schema and append it."""
        sample = read_sql(self.engine, """
            SELECT epa_id, make, model, year, comb08::float8 AS comb08,
                   cylinders::float8 AS cylinders, displ::float8 AS displ
            FROM cars_public_epa ORDER BY epa_id""")
        sample["Origin"] = sample["make"].map(ORIGIN_OF)
        public = pd.DataFrame({
            "Car": (sample["make"].str.strip() + " " + sample["model"].str.strip()),
            "MPG": sample["comb08"].astype(float),
            "Cylinders": sample["cylinders"],
            "Displacement": (sample["displ"] * LITRES_TO_CUBIC_INCHES).round(1),
            "Horsepower": np.nan,      # not published in the EPA file
            "Weight": np.nan,          # not published in the EPA file
            "Acceleration": np.nan,    # not published in the EPA file
            "Model": sample["year"] % 100,
            "Origin": sample["Origin"],
        })
        public["source"] = "epa_public"
        self.public = public.reset_index(drop=True)

        original = self.df.assign(source="original")
        original["Origin"] = original["Origin"].astype(str)
        self.df = pd.concat([original, self.public], ignore_index=True)
        self.df["Origin"] = self.df["Origin"].astype("category")
        self.baseline = self.df.copy()
        return self.df

    def source_summary(self) -> pd.DataFrame:
        """Row count and years covered by each data source."""
        return self.df.groupby("source", observed=True).agg(
            rows=("Car", "size"), first_year=("Model", "min"), last_year=("Model", "max"))

    def save_clean(self) -> pd.DataFrame:
        """Write the current cleaned data to the cars_clean table in Neon."""
        out = self.df[SCHEMA + ["source"]].copy()
        out["Origin"] = out["Origin"].astype(str)
        out.columns = [c.lower() for c in out.columns]
        rows = replace_rows(self.engine, "cars_clean", out)
        return pd.DataFrame({"table": ["cars_clean"], "rows_written": [rows]})

    # ------------------------------------------------------------------ 3.3
    def duplicates_report(self) -> pd.DataFrame:
        """Return every row that has an exact duplicate (all columns equal)."""
        return self.df[self.df.duplicated(keep=False)].sort_values(["Car", "Model"])

    def drop_duplicates(self) -> pd.DataFrame:
        """Remove exact duplicate rows, keeping the first occurrence."""
        self.df = self.df.drop_duplicates().reset_index(drop=True)
        return self.df

    # ------------------------------------------------------------------ 3.4
    def drop_missing(self, axis: int = 0) -> pd.DataFrame:
        """Return a COPY without missing values: axis=0 drops rows, axis=1 drops columns."""
        return self.df.dropna(axis=axis)

    def impute(self, column: str, strategy: str = "mean", inplace: bool = False) -> pd.DataFrame:
        """Fill NaN in one column with its mean, median or mode (on a copy unless inplace=True)."""
        target = self.df if inplace else self.df.copy()
        if strategy == "mode":
            value = target[column].mode()[0]
        elif strategy in ("mean", "median"):
            value = getattr(target[column], strategy)()
        else:
            raise ValueError("strategy must be 'mean', 'median' or 'mode'")
        target[column] = target[column].fillna(value)
        return target

    # ------------------------------------------------------------------ 3.5
    def center_stats(self, column: str) -> pd.Series:
        """Mean, median and skewness of one column, used to choose mean vs median."""
        s = self.df[column]
        return pd.Series({"mean": s.mean(), "median": s.median(), "skew": s.skew()}).round(3)

    def distribution_plot(self, column: str):
        """Histogram of one column with dashed lines at its mean and median."""
        s = self.df[column].dropna()
        fig = px.histogram(self.df, x=column, nbins=30,
                           title=f"Distribution of {column}",
                           labels={column: column, "count": "Number of cars"})
        fig.add_vline(x=s.mean(), line_dash="dash", line_color="firebrick",
                      annotation_text=f"mean {s.mean():.1f}", annotation_position="top right")
        fig.add_vline(x=s.median(), line_dash="dash", line_color="seagreen",
                      annotation_text=f"median {s.median():.1f}", annotation_position="top left")
        fig.update_layout(yaxis_title="Number of cars")
        return fig

    # ------------------------------------------------------------------ 3.6
    def simple_impute(self, columns, strategy: str = "median") -> pd.DataFrame:
        """Fit a scikit-learn SimpleImputer on the columns and fill their NaN in self.df."""
        self.imputer = SimpleImputer(strategy=strategy)
        self.imputer.fit(self.df[columns])                 # learn the statistic
        self.df[columns] = self.imputer.transform(self.df[columns])  # apply it
        return self.df

    def group_impute(self, column: str, by: str = "Cylinders", strategy: str = "median") -> pd.DataFrame:
        """Fill NaN in column with the median (or mean) of the cars that share the same `by` value."""
        self.df[column] = self.df.groupby(by)[column].transform(
            lambda group: group.fillna(getattr(group, strategy)()))
        return self.df

    def regression_impute(self, target: str, predictors) -> pd.DataFrame:
        """Fill NaN in target with a linear regression fitted on rows where target is known."""
        from sklearn.linear_model import LinearRegression
        known = self.df[target].notna() & self.df[predictors].notna().all(axis=1)
        unknown = self.df[target].isna() & self.df[predictors].notna().all(axis=1)
        model = LinearRegression().fit(self.df.loc[known, predictors], self.df.loc[known, target])
        self.df.loc[unknown, target] = model.predict(self.df.loc[unknown, predictors])
        return self.df

    # ------------------------------------------------------------------ 3.7
    def compare_before_after(self, columns=("MPG", "Displacement", "Horsepower", "Weight")) -> pd.DataFrame:
        """Side-by-side shape, missing, duplicates and statistics before and after cleaning."""
        rows = {}
        for label, data in (("before", self.baseline), ("after", self.df)):
            stats = {"rows": len(data), "missing_cells": int(data.isna().sum().sum()),
                     "duplicate_rows": int(data.duplicated().sum())}
            for col in columns:
                stats[f"{col}_mean"] = round(data[col].mean(), 2)
                stats[f"{col}_median"] = round(data[col].median(), 2)
                stats[f"{col}_std"] = round(data[col].std(), 2)
            rows[label] = stats
        return pd.DataFrame(rows)

    def before_after_plot(self, column: str):
        """Box plots of one column before and after cleaning."""
        both = pd.concat([
            pd.DataFrame({column: self.baseline[column], "stage": "before"}),
            pd.DataFrame({column: self.df[column], "stage": "after"}),
        ])
        fig = px.box(both, x="stage", y=column, color="stage",
                     title=f"{column} before vs after cleaning",
                     labels={"stage": "Stage", column: column})
        return fig.update_layout(showlegend=False)
