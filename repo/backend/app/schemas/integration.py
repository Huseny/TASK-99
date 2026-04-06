from pydantic import BaseModel, Field


class IntegrationClientCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    organization_id: int | None = None
    rate_limit_rpm: int | None = Field(default=None, ge=1, le=2000)


class IntegrationClientCreateOut(BaseModel):
    client_id: str
    client_secret: str
    rate_limit_rpm: int


class IntegrationClientRotateOut(BaseModel):
    client_id: str
    client_secret: str


class SISStudentRecord(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=100)
    is_active: bool = True


class QbankFormRecord(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    criteria: list[dict] = Field(min_length=1)


class SISStudentsSyncIn(BaseModel):
    import_id: str = Field(min_length=1, max_length=120)
    students: list[SISStudentRecord] = Field(min_length=1)


class QbankFormsImportIn(BaseModel):
    import_id: str = Field(min_length=1, max_length=120)
    forms: list[QbankFormRecord] = Field(min_length=1)
