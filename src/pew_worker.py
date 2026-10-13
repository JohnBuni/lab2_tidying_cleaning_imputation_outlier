from pathlib import Path

import pandas as pd


class PewWorker:
    """Load, reshape, and summarize PEW survey data."""

    # Matches d_income_<country> and d_income2_<country>
    # Group 1 = measure (income / income2), group 2 = country suffix
    INCOME_PATTERN = r"^d_(income2?)_(.+)$"

    # Columns that identify a respondent; everything else can be
    # joined back later on "id" if needed
    ID_COLUMNS = ["id", "country", "weight"]

    # Pew non-response codes (Don't know / Refused).
    # Verify against the codebook before relying on these.
    NON_RESPONSE_CODES = [98, 99]

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

        # Blank cells (" ") mean "question not asked" -> treat as missing.
        # utf-8-sig strips the byte-order mark from the first column name.
        self.df = pd.read_csv(
            self.file_path,
            low_memory=False,
            na_values=[" ", ""],
            encoding="utf-8-sig"
        )

        # Normalize column names: drop stray BOMs/spaces, lowercase
        self.df.columns = (
            self.df.columns.astype(str)
            .str.replace("\ufeff", "", regex=False)
            .str.strip()
            .str.lower()
        )

        return self.df

    def melt_income(self) -> pd.DataFrame:
        """Reshape country income columns into a tidy long table."""
        if self.df is None:
            raise ValueError("Call load() before melt_income().")

        income_columns = self.df.filter(
            regex=self.INCOME_PATTERN
        ).columns.tolist()

        if not income_columns:
            near = [c for c in self.df.columns if "income" in c]
            raise ValueError(
                "No income columns matched "
                f"{self.INCOME_PATTERN!r}. "
                f"Loaded {self.df.shape[1]} columns from {self.file_path}. "
                f"Columns containing 'income': {near[:10]}"
            )

        missing_ids = [
            col for col in self.ID_COLUMNS
            if col not in self.df.columns
        ]
        if missing_ids:
            raise ValueError(f"Missing ID columns: {missing_ids}")

        # Melt using only the identifying columns
        melted = self.df.melt(
            id_vars=self.ID_COLUMNS,
            value_vars=income_columns,
            var_name="income_variable",
            value_name="income_code"
        )

        # Drop rows for questions the respondent was never asked
        melted = melted.dropna(subset=["income_code"])

        # Split the column name into its two variables
        parts = melted["income_variable"].str.extract(
            self.INCOME_PATTERN
        )
        melted["measure"] = parts[0]
        melted["country_name"] = parts[1]

        # Treat Don't know / Refused as missing values
        melted["income_code"] = melted["income_code"].mask(
            melted["income_code"].isin(self.NON_RESPONSE_CODES)
        )

        self.melted_df = melted.reset_index(drop=True)

        return self.melted_df

    def summary(self) -> pd.DataFrame:
        """Count valid income responses per country and measure."""
        if self.melted_df is None:
            raise ValueError(
                "Call melt_income() before summary()."
            )

        return (
            self.melted_df
            .groupby(["country_name", "measure"])["income_code"]
            .count()
            .unstack("measure", fill_value=0)
            .rename_axis(columns=None)
            .reset_index()
            .sort_values("country_name")
            .reset_index(drop=True)
        )