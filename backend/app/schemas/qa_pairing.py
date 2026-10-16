from typing import Literal

from pydantic import BaseModel, Field


class QAPairItem(BaseModel):
    pair_id: int = Field(description="Sequential number of this pair, starting at 1")
    type: Literal["main", "follow_up"] = Field(
        description="main = a new question; follow_up = digs deeper into the answer of an earlier pair"
    )
    parent_pair_id: int | None = Field(
        default=None, description="For follow_up only: the pair_id of the earlier pair it follows up on"
    )
    question_turns: list[int] = Field(
        description="Turn numbers of the interviewer turns that ask this question, incl. any clarification"
    )
    answer_turns: list[int] = Field(
        description="Turn numbers of the candidate turns that answer it; empty if it was not answered"
    )
    sub_questions: list[str] = Field(
        default_factory=list,
        description="For a multi-part question: each part as a short phrase; empty for a single question",
    )


class QAPairingResult(BaseModel):
    """Interview questions paired with the candidate's answers, by turn number."""

    pairs: list[QAPairItem] = Field(description="One entry per interview question, in spoken order")
