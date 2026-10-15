from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

AnalysisKind = Literal["cv", "jd"]
Nonblank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")


class Evidence(ExtractionModel):
    source_number: int = Field(ge=1)
    # Keep quotes verbatim (including surrounding whitespace).
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def nonblank_quote(self) -> "Evidence":
        if not self.quote.strip():
            raise ValueError("Evidence quote must not be blank")
        return self


class ProfileFact(ExtractionModel):
    value: Nonblank
    evidence: list[Evidence] = Field(min_length=1)


class CVProfile(ExtractionModel):
    headline: list[ProfileFact]
    skills: list[ProfileFact]
    experience: list[ProfileFact]
    education: list[ProfileFact]
    certifications: list[ProfileFact]
    languages: list[ProfileFact]


class JDProfile(ExtractionModel):
    title: list[ProfileFact]
    employer: list[ProfileFact]
    required_skills: list[ProfileFact]
    preferred_skills: list[ProfileFact]
    responsibilities: list[ProfileFact]
    qualifications: list[ProfileFact]
    languages: list[ProfileFact]


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: AnalysisKind


class AnalysisSource(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    number: int = Field(ge=1)
    document_id: UUID
    chunk_id: UUID
    chunk_index: int = Field(ge=0)
    text: str


class AnalysisMessage(BaseModel):
    role: Literal["system", "user"]
    content: str


class AnalysisProvenance(BaseModel):
    schema_version: str
    prompt_version: str
    provider: str
    model: str
    timeout_seconds: float
    max_output_tokens: int
    max_context_chars: int
    messages: list[AnalysisMessage]


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    kind: AnalysisKind
    version: int = Field(ge=1)
    status: Literal["completed", "insufficient_evidence"]
    document_checksum: str
    created_at: datetime


class AnalysisResponse(AnalysisSummary):
    profile: CVProfile | JDProfile
    sources: list[AnalysisSource]
    provenance: AnalysisProvenance

    @model_validator(mode="after")
    def matching_profile(self) -> "AnalysisResponse":
        model = CVProfile if self.kind == "cv" else JDProfile
        if not isinstance(self.profile, model):
            raise ValueError("Profile does not match analysis kind")
        return self


class AnalysisListResponse(BaseModel):
    analyses: list[AnalysisSummary]
