
from pathlib import Path

import pandas as pd


class PewWorker:
    """Load, reshape, and summarize PEW survey data."""

    def __init__(self, file_path):
        """Initialize the worker with the CSV file path."""
        self.file_path = Path(file_path)
        self.df = None
        self.melted_df = None

    def load(self) -> pd.DataFrame:
        """Load the PEW CSV dataset into a DataFrame."""
        if not self.file_path.is_file():
            raise FileNotFoundError(
                f"Dataset not found: {self.file_path}"
            )

        self.df = pd.read_csv(
            self.file_path,
            low_memory=False
        )

        return self.df

    def melt_income(self) -> pd.DataFrame:
        """Reshape income columns into income and count columns."""
        if self.df is None:
            raise ValueError("Call load() before melt_income().")

        income_columns = [
            col for col in self.df.columns
            if "income" in str(col).lower()
        ]

        if not income_columns:
            raise ValueError(
                "No income columns were found. "
                "Check the dataset's column names."
            )

        id_columns = [
            col for col in self.df.columns
            if col not in income_columns
        ]

        self.melted_df = self.df.melt(
            id_vars=id_columns,
            value_vars=income_columns,
            var_name="income",
            value_name="count"
        )

        return self.melted_df

    def summary(self) -> pd.DataFrame:
        """Summarize counts by income category."""
        if self.melted_df is None:
            raise ValueError(
                "Call melt_income() before summary()."
            )

        result = self.melted_df.copy()
        result["count"] = pd.to_numeric(
            result["count"],
            errors="coerce"
        )

        return (
            result.groupby("income", as_index=False)["count"]
            .sum(min_count=1)
            .sort_values("income")
        )
