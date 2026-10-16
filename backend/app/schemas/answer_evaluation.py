from typing import Literal

from pydantic import BaseModel, Field


class AnswerEvaluationItem(BaseModel):
    pair_id: int = Field(description="The pair_id of the evaluated question-answer pair")
    relevance: int = Field(description="1-5: does the answer address the question that was asked")
    accuracy: int = Field(description="1-5: are the facts and claims in the answer correct")
    completeness: int = Field(description="1-5: does the answer cover all parts of the question")
    quality: int = Field(description="1-5: clarity, structure and depth of the answer")
    accuracy_verdict: Literal["supported", "contradicted", "not_verifiable"] = Field(
        description="supported / contradicted by the cited passages, or not_verifiable from them"
    )
    cited_chunks: list[str] = Field(
        default_factory=list,
        description="Labels (e.g. K3) of the passages used for the verdict; only labels listed for this pair",
    )
    justification: str = Field(description="One or two short sentences explaining the scores")


class AnswerEvaluationResult(BaseModel):
    """Evaluation of each answered interview question."""

    evaluations: list[AnswerEvaluationItem] = Field(description="One entry per pair in the input")
