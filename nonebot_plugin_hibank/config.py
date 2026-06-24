from __future__ import annotations

from pydantic import BaseModel, Field


class HibankConfig(BaseModel):
    hibank_base_url: str = Field(default="https://hi.zzz.moe")
    hibank_timeout: float = Field(default=30)
    hibank_verify_ssl: bool = Field(default=False)
    hibank_branch_page_size: int = Field(default=30)
