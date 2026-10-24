"""Export prepared tables (Polars) to the CSV/Parquet layout that ``xferbench validate`` reads."""

from xferbench.data_preparation.export_data.writer import export_table

__all__ = ["export_table"]
