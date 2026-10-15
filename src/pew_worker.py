from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


class PewWorker:
    """Load, reshape, label, and summarize PEW survey income data."""

    # Matches d_income_<country> and d_income2_<country>
    # Group 1 = measure (income / income2), group 2 = country suffix
    INCOME_PATTERN = r"^d_(income2?)_(.+)$"

    # Columns that identify a respondent
    ID_COLUMNS = ["id", "country", "weight"]

    # The metadata file is a DDI 2.5 codebook
    DDI_NS = {"d": "ddi:codebook:2_5"}

    def __init__(self, file_path, metadata_path=None):
        """Store the CSV path and, optionally, the metadata XML path."""
        self.file_path = Path(file_path)
        self.metadata_path = Path(metadata_path) if metadata_path else None
        self.df = None
        self.melted_df = None
        self.value_labels = {}   # variable -> {code: label}

    def load(self) -> pd.DataFrame:
        """Load the PEW CSV dataset into a DataFrame."""
        if not self.file_path.is_file():
            raise FileNotFoundError(f"Dataset not found: {self.file_path}")

        # Blank cells (" ") mean "question not asked" -> treat as missing
        self.df = pd.read_csv(
            self.file_path,
            low_memory=False,
            na_values=[" ", ""],
            encoding="utf-8-sig",
        )
        self.df.columns = self.df.columns.str.strip().str.lower()
        return self.df

    def load_metadata(self, metadata_path=None) -> int:
        """Read the value labels (code -> text) from the metadata XML."""
        if metadata_path is not None:
            self.metadata_path = Path(metadata_path)
        if self.metadata_path is None or not self.metadata_path.is_file():
            raise FileNotFoundError(f"Metadata XML not found: {self.metadata_path}")

        ns = self.DDI_NS
        root = ET.parse(self.metadata_path).getroot()
        for var in root.iter(f"{{{ns['d']}}}var"):
            self.value_labels[var.get("name", "").lower()] = {
                int(float(cat.findtext("d:catValu", "", ns))):
                    cat.findtext("d:labl", "", ns).strip()
                for cat in var.findall("d:catgry", ns)
            }
        return len(self.value_labels)

    def melt_income(self) -> pd.DataFrame:
        """Reshape country income columns into a tidy long table."""
        if self.df is None:
            raise ValueError("Call load() before melt_income().")

        income_columns = self.df.filter(regex=self.INCOME_PATTERN).columns.tolist()
        if not income_columns:
            raise ValueError(f"No income columns matched {self.INCOME_PATTERN!r}.")

        melted = self.df.melt(
            id_vars=self.ID_COLUMNS,
            value_vars=income_columns,
            var_name="income_variable",
            value_name="income_code",
        )

        # Drop rows for questions the respondent was never asked
        melted = melted.dropna(subset=["income_code"])
        melted["income_code"] = melted["income_code"].astype(int)

        # Split the column name into its two variables
        parts = melted["income_variable"].str.extract(self.INCOME_PATTERN)
        melted["measure"] = parts[0]
        melted["country_name"] = parts[1]

        self.melted_df = melted.reset_index(drop=True)
        return self.melted_df

    def add_metadata_columns(self) -> pd.DataFrame:
        """Add country_label, income_label and response_status from the codebook."""
        if self.melted_df is None:
            raise ValueError("Call melt_income() before add_metadata_columns().")
        if not self.value_labels:
            raise ValueError("Call load_metadata() before add_metadata_columns().")

        m = self.melted_df

        # 1. Full country name for the numeric country code
        m["country_label"] = m["country"].map(self.value_labels["country"])

        # 2. Text of the income bracket the respondent chose.
        #    A few codes are missing from the codebook (98 in France's
        #    follow-up question), so Pew's standard 98/99 meaning is used.
        fallback = {98: "Don't know", 99: "Refused"}
        m["income_label"] = [
            self.value_labels.get(var, {}).get(code, fallback.get(code))
            for var, code in zip(m["income_variable"], m["income_code"])
        ]

        # 3. Whether the answer is a real income. Non-response codes differ
        #    by question (98/99 vs 8/9), so the label text decides.
        label = m["income_label"].fillna("")
        m["response_status"] = np.select(
            [label.str.contains("don.t know", case=False, regex=True),
             label.str.contains("refused", case=False, regex=True)],
            ["dont_know", "refused"],
            default="valid",
        )

        self.melted_df = m
        return self.melted_df

    def summary(self) -> pd.DataFrame:
        """Count valid income responses per country and measure."""
        if self.melted_df is None:
            raise ValueError("Call melt_income() before summary().")

        data = self.melted_df
        if "response_status" in data.columns:
            data = data[data["response_status"] == "valid"]

        return (
            data.groupby(["country_name", "measure"])["income_code"]
            .count()
            .unstack("measure", fill_value=0)
            .rename_axis(columns=None)
            .reset_index()
            .sort_values("country_name")
            .reset_index(drop=True)
        )
