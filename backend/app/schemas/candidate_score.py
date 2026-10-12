from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    score: int = Field(ge=0, le=100, description="0-100 score for this dimension")
    justification: str = Field(description="1-2 sentences explaining the score")
    evidence: list[str] = Field(default_factory=list, description="Up to 3 short quotes from the CV")


class CandidateScoring(BaseModel):
    technical_skills: DimensionScore
    experience: DimensionScore
    qualifications: DimensionScore