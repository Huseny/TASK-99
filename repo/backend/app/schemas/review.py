from datetime import datetime

from pydantic import BaseModel, Field


class ScoringFormCreate(BaseModel):
    name: str
    organization_id: int
    criteria: list[dict]


class ReviewRoundCreate(BaseModel):
    name: str
    term_id: int
    section_id: int
    scoring_form_id: int
    identity_mode: str = "BLIND"


class ReviewRoundOut(BaseModel):
    id: int
    name: str
    term_id: int
    section_id: int
    scoring_form_id: int
    identity_mode: str
    status: str


class ManualAssignmentIn(BaseModel):
    reviewer_id: int
    student_id: int


class AutoAssignmentIn(BaseModel):
    student_ids: list[int]
    reviewers_per_student: int = Field(default=2, ge=1, le=5)


class AssignmentOut(BaseModel):
    id: int
    round_id: int
    reviewer_id: int
    student_id: int | None
    student_ref: str | None = None
    section_id: int
    assigned_manually: bool


class ScoreSubmitIn(BaseModel):
    assignment_id: int
    criterion_scores: dict[str, float]
    comment: str | None = None


class ScoreOut(BaseModel):
    id: int
    assignment_id: int
    total_score: float
    submitted_at: datetime


class OutlierOut(BaseModel):
    id: int
    round_id: int
    student_id: int
    score_id: int
    median_score: float
    deviation: float
    resolved: bool


class RecheckCreateIn(BaseModel):
    round_id: int
    student_id: int
    section_id: int
    reason: str


class RecheckAssignIn(BaseModel):
    reviewer_id: int
