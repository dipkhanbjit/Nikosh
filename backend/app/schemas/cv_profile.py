from pydantic import BaseModel, Field


class Education(BaseModel):
    degree: str = Field(description="Degree name, e.g. 'BSc', 'MSc', 'HSC'")
    field: str | None = Field(default=None, description="Subject or major, e.g. 'Computer Science and Engineering'")
    institution: str | None = Field(default=None, description="University, college or school name")
    graduation_year: int | None = Field(default=None, description="Year completed or expected, e.g. 2024")
    result: str | None = Field(default=None, description="CGPA or grade exactly as written, e.g. '3.85/4.00'")


class WorkExperience(BaseModel):
    title: str = Field(description="Job title")
    company: str | None = Field(default=None, description="Company or organization name")
    start_date: str | None = Field(default=None, description="Start date as YYYY-MM (use YYYY-01 if only the year is known)")
    end_date: str | None = Field(default=None, description="End date as YYYY-MM, or 'present' if this is the current job")
    summary: str | None = Field(default=None, description="One sentence on the main responsibilities or achievements")


class CVProfile(BaseModel):
    """Structured information extracted from a CV."""

    full_name: str | None = Field(default=None, description="Candidate's full name")
    email: str | None = Field(default=None, description="Email address")
    phone: str | None = Field(default=None, description="Phone number as written")
    summary: str | None = Field(default=None, description="Two-sentence professional summary of the candidate")
    skills: list[str] = Field(default_factory=list, description="Technical and professional skills, tools, languages and frameworks")
    education: list[Education] = Field(default_factory=list)
    work_history: list[WorkExperience] = Field(default_factory=list, description="Professional jobs and internships, most recent first")
    certifications: list[str] = Field(default_factory=list, description="Certifications and licenses")