from __future__ import annotations

from typing import override


class HandoffError(Exception):
    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code, detail)

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"
