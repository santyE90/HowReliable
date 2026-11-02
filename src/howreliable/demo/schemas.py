"""Versioned local demo responses; frozen prediction schemas remain separate."""

from typing import Any, Literal

from pydantic import Field

from howreliable.api.schemas import APIModel


class DemoResponse(APIModel):
    schema_version: Literal["howreliable-demo-1.0"] = "howreliable-demo-1.0"


class HistoricalVehicle(APIModel):
    id: str
    make: str
    model: str
    year: int


class VehiclePage(DemoResponse):
    items: list[HistoricalVehicle]
    total: int
    limit: int
    offset: int
    makes: list[str]
    models: list[str]
    years: list[int]


class Resolution(DemoResponse):
    status: Literal["matched", "unmatched", "ambiguous"]
    candidates: list[HistoricalVehicle]


class TimelineBin(APIModel):
    month: str | None
    unique_report_count: int = Field(ge=0)
    source_row_count: int = Field(ge=0)


class ComponentCount(APIModel):
    category: str
    source_row_count: int = Field(ge=0)
    unique_report_count: int = Field(ge=0)


class HistoricalSummary(DemoResponse):
    vehicle: HistoricalVehicle
    source_row_count: int = Field(ge=0)
    unique_report_count: int = Field(ge=0)
    missing_report_date_rows: int = Field(ge=0)
    first_report_date: str | None
    last_report_date: str | None
    timeline_policy: str
    timeline: list[TimelineBin]
    components: list[ComponentCount]
    provenance: dict[str, Any]
    limitation: str


class PredictionLink(DemoResponse):
    status: Literal["supported", "unsupported", "ambiguous"]
    cohort_ids: list[str]
    prediction_url: str | None
    history_cutoff: Literal["2022-12-31"] = "2022-12-31"
    forecast_start: Literal["2023-01-01"] = "2023-01-01"
    forecast_end: Literal["2023-12-31"] = "2023-12-31"
    interpretation: str = (
        "Historical 2023 complaint-activity forecast; not a current forecast or individual "
        "vehicle failure probability."
    )


class ExploratorySummary(DemoResponse):
    scope: Literal["global_bounded_G1_sample_only"] = "global_bounded_G1_sample_only"
    vehicle_specific: Literal[False] = False
    predates_current_rules: Literal[True] = True
    summary: dict[str, Any]
    provenance: dict[str, Any]
