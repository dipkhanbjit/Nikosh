from typing import Literal

from pydantic import BaseModel, Field

Rating = Literal["met", "partial", "unmet"]


class RequirementMatch(BaseModel):
    requirement_id: int = Field(description="The number of the requirement exactly as given in the list")
    rating: Rating = Field(
        description="met = clearly satisfied; partial = related or weaker evidence; unmet = no evidence in the CV"
    )
    evidence: str = Field(
        description="Short quote or close paraphrase from the CV that supports the rating, "
                    "or 'No evidence found in the CV' when unmet"
    )


class ScreeningResult(BaseModel):
    """Requirement-by-requirement assessment of one CV."""

    matches: list[RequirementMatch] = Field(description="Exactly one entry for every requirement in the list")