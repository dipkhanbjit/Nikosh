from typing import Literal

from pydantic import BaseModel, Field


class RequirementMappingItem(BaseModel):
    requirement_id: int = Field(description="The number of the requirement (R1 -> 1)")
    coverage: Literal["demonstrated", "partial", "not_covered"] = Field(
        description="demonstrated / partial / not_covered by the candidate's answers"
    )
    supporting_pairs: list[int] = Field(
        default_factory=list,
        description="pair_ids of the answers that support this requirement; empty when not_covered",
    )
    justification: str = Field(description="One or two short sentences explaining the coverage")


class RequirementMappingResult(BaseModel):
    """Coverage of each job requirement by the interview answers."""

    mappings: list[RequirementMappingItem] = Field(description="One entry per requirement in the input")
