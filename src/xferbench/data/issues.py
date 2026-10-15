"""Structured data-quality issues with table/field/row identifiers and corrective suggestions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass
class Issue:
    severity: Severity
    code: str
    message: str
    table: str | None = None
    column: str | None = None
    row_ids: list[str] = field(default_factory=list)
    count: int = 0
    suggestion: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        loc = ".".join(x for x in (self.table, self.column) if x)
        rows = f" rows={self.row_ids[:5]}" if self.row_ids else ""
        hint = f" -> {self.suggestion}" if self.suggestion else ""
        return f"[{self.severity}] {self.code} {loc}: {self.message}{rows}{hint}"


class DataError(Exception):
    """Raised when inputs cannot be loaded into the canonical contract."""

    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))
