from pathlib import Path
import re

import pandas as pd


class BillboardWorker:
    """Load and tidy Billboard weekly chart rankings."""

    def __init__(self, file_path="data/billboard.csv"):
        """Store the CSV path and initialize the raw and tidy data."""
        self.file_path = Path(file_path)
        self.df = None
        self.melted_df = None

    def load(self, source="csv", engine=None) -> pd.DataFrame:
        """Load the local CSV or the public.billboard_raw Neon table."""
        if source == "csv":
            result = pd.read_csv(self.file_path)
        elif source == "neon":
            from .db import get_engine, read_sql

            owns_engine = engine is None
            engine = get_engine() if owns_engine else engine
            try:
                result = read_sql(engine, "SELECT * FROM public.billboard_raw")
            finally:
                if owns_engine:
                    engine.dispose()
        else:
            raise ValueError("source must be 'csv' or 'neon'.")
        self.df = result
        self.melted_df = None
        return self.df

    def melt_weeks(self) -> pd.DataFrame:
        """Reshape wk1, wk2, and other weekly columns into week and rank."""
        if self.df is None:
            raise ValueError("Call load() before melt_weeks().")
        week_columns = [
            column for column in self.df.columns
            if re.fullmatch(
                r"(?:wk[1-9]\d*|[1-9]\d*(?:st|nd|rd|th) week)",
                str(column).strip(), re.IGNORECASE
            )
        ]
        if not week_columns:
            raise ValueError("Expected weekly columns such as 1st week, 2nd week, or wk1.")
        if {"week", "rank"}.intersection(self.df.columns):
            raise ValueError("Input already contains a week or rank column.")
        week_columns.sort(key=lambda column: int(re.search(r"\d+", str(column)).group()))
        id_columns = [c for c in self.df.columns if c not in week_columns]
        self.melted_df = self.df.melt(
            id_vars=id_columns,
            value_vars=week_columns,
            var_name="week",
            value_name="rank",
        )
        return self.melted_df

    def clean_week_column(self) -> pd.DataFrame:
        """Strip, lowercase, remove ordinal suffixes, and extract integer weeks."""
        if self.melted_df is None:
            raise ValueError("Call melt_weeks() before clean_week_column().")
        labels = (
            self.melted_df["week"].astype("string")
            .str.strip()
            .str.lower()
            .str.replace(r"(?<=\d)(st|nd|rd|th)\b", "", regex=True)
        )
        weeks = pd.to_numeric(labels.str.extract(r"(\d+)", expand=False), errors="raise")
        if weeks.isna().any() or ((weeks < 1) | (weeks % 1 != 0)).any():
            raise ValueError("Week values must be positive whole numbers.")
        self.melted_df["week"] = weeks.astype("int64")
        return self.melted_df

    def drop_empty_ranks(self) -> pd.DataFrame:
        """Remove missing or blank rankings and convert remaining ranks to numbers."""
        if self.melted_df is None:
            raise ValueError("Call melt_weeks() before drop_empty_ranks().")
        result = self.melted_df.copy()
        result["rank"] = pd.to_numeric(
            result["rank"].replace(r"^\s*$", float("nan"), regex=True),
            errors="raise",
        )
        self.melted_df = result.dropna(subset=["rank"]).reset_index(drop=True)
        return self.melted_df

    def add_chart_date(self, date_column="date entered") -> pd.DataFrame:
        """Add chart_date as the entry date plus seven days per week after week one."""
        if self.melted_df is None:
            raise ValueError("Call melt_weeks() before add_chart_date().")
        if date_column not in self.melted_df.columns:
            raise ValueError(f"Entry-date column not found: {date_column!r}.")
        if not pd.api.types.is_integer_dtype(self.melted_df["week"]):
            raise ValueError("Call clean_week_column() before add_chart_date().")
        entered = pd.to_datetime(self.melted_df[date_column], errors="raise")
        if entered.isna().any():
            raise ValueError("Entry dates must not be missing.")
        self.melted_df["chart_date"] = entered + pd.to_timedelta(
            (self.melted_df["week"] - 1) * 7, unit="D"
        )
        return self.melted_df

    def plot_rankings(self, tracks=None):
        """Return a Plotly ranking chart with rank one at the top."""
        import plotly.express as px

        if self.melted_df is None:
            raise ValueError("Run the tidying methods before plot_rankings().")
        if not pd.api.types.is_integer_dtype(self.melted_df["week"]):
            raise ValueError("Call clean_week_column() before plot_rankings().")
        tracks = ["Maria, Maria", "Music", "Say My Name"] if tracks is None else tracks
        data = self.melted_df.loc[self.melted_df["track"].isin(tracks)].copy()
        data["rank"] = pd.to_numeric(data["rank"], errors="raise")
        data = data.dropna(subset=["rank"]).sort_values("week")
        if data.empty:
            raise ValueError("No ranked observations match the selected tracks.")
        data["song"] = data["artist"] + " — " + data["track"]
        figure = px.line(
            data, x="week", y="rank", color="song", markers=True,
            title="Billboard Ranking Trajectories",
            labels={"week": "Chart week", "rank": "Rank (1 = highest)", "song": "Song"},
        )
        figure.update_yaxes(autorange="reversed")
        return figure
