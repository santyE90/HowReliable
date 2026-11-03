"""Versioned transient manual pricing evidence. No provider or historical data dependency."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator

from howreliable.api.schemas import APIModel
from howreliable.demo.purchase_schemas import PurchaseAssessmentRequest
from howreliable.domain.reliability import VehicleAssociation

State = Literal["yes", "no", "unknown"]
TaxBasis = Literal[
    "taxes_and_fees_excluded",
    "taxes_excluded_fees_included",
    "taxes_and_fees_included",
    "unknown",
]


def canonical_date(value: object) -> date | None:
    if value is None or type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("date must be canonical YYYY-MM-DD")
    return date.fromisoformat(value)


class PricingVehicle(APIModel):
    make: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    year: int | None = Field(default=None, ge=1886, le=2100)
    trim: str | None = Field(default=None, max_length=100)
    powertrain: str | None = Field(default=None, max_length=100)
    transmission: Literal["automatic", "manual", "cvt", "dct", "other", "unknown"] = "unknown"
    drivetrain: Literal["fwd", "rwd", "awd", "four_wd", "other", "unknown"] = "unknown"
    body_style: str | None = Field(default=None, max_length=100)
    province: (
        Literal["AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"] | None
    ) = None
    city: str | None = Field(default=None, max_length=100)
    seller_type: Literal["dealer", "private", "unknown"] = "unknown"
    condition_status: Literal["no_known_issues_reported", "issues_reported", "unknown"] = "unknown"
    accident_history: State = "unknown"
    title_status: Literal["normal_reported", "salvage", "rebuilt", "other", "unknown"] = "unknown"

    @field_validator("make", "model", "trim", "powertrain", "body_style", "city")
    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("control characters are not allowed")
        return VehicleAssociation.normalize_required_text(value)


class ListingReference(APIModel):
    source_name: str | None = Field(default=None, max_length=100)
    source_listing_id: str | None = Field(default=None, max_length=120)
    listing_url: str | None = Field(default=None, max_length=2048)

    @field_validator("source_name", "source_listing_id", "listing_url")
    @classmethod
    def clean_reference(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("control characters are not allowed")
        return value.strip()

    @field_validator("source_name")
    @classmethod
    def normalize_source(cls, value: str | None) -> str | None:
        return VehicleAssociation.normalize_required_text(value) if value else None

    @field_validator("listing_url")
    @classmethod
    def inert_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or "?" in value
            or "#" in value
            or "\\" in value
            or any(c.isspace() for c in value)
        ):
            raise ValueError(
                "use an inert public HTTP(S) reference without credentials/query/fragment"
            )
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if (
                "." not in host
                or host.endswith((".local", ".internal", ".localhost"))
                or not re.fullmatch(r"[a-zA-Z0-9.-]+", host)
                or all(c.isdigit() or c == "." for c in host)
            ):
                raise ValueError("public hostname required") from None
        else:
            if not address.is_global:
                raise ValueError("non-public addresses are not allowed")
        port = parsed.port
        authority = f"[{host}]" if ":" in host else host
        if port is not None and (parsed.scheme, port) not in {("http", 80), ("https", 443)}:
            authority += f":{port}"
        return urlunsplit((parsed.scheme, authority, parsed.path, "", ""))


class PricingSubject(PricingVehicle):
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1886, le=2100)
    odometer_km: int | None = Field(default=None, ge=0)
    asking_price_cad: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    tax_fee_basis: TaxBasis = "unknown"
    subject_reference: ListingReference | None = None

    @field_validator("asking_price_cad", mode="before")
    @classmethod
    def price(cls, value: object) -> Decimal | None:
        return PurchaseAssessmentRequest.parse_price(value)

    @model_validator(mode="after")
    def required_identity(self) -> PricingSubject:
        if not self.make or not self.model:
            raise ValueError("subject identity is required")
        return self


class ManualComparable(ListingReference):
    entry_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    vehicle: PricingVehicle
    odometer: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)
    odometer_unit: Literal["km", "mi", "unknown"] = "unknown"
    asking_price: Decimal | None = None
    currency: Literal["CAD", "USD", "other", "unknown"] = "unknown"
    price_basis: Literal[
        "cash_asking", "monthly_payment", "valuation", "transaction", "unknown"
    ] = "unknown"
    tax_fee_basis: TaxBasis = "unknown"
    observed_on: date | None = None
    listed_on: date | None = None
    listing_status: Literal["active_reported", "inactive_reported", "unknown"] = "unknown"
    permission_basis: Literal[
        "user_owned", "explicit_permission", "licensed", "synthetic", "unknown"
    ] = "unknown"
    permission_reference: str | None = Field(default=None, max_length=200)
    permission_attested: bool = False
    verification_status: Literal["user_entered_unverified", "user_rechecked"] = (
        "user_entered_unverified"
    )
    is_subject_vehicle: State = "unknown"
    duplicate_of_entry_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,40}$")
    possible_duplicate_of_entry_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]{1,40}$"
    )

    @field_validator("observed_on", "listed_on", mode="before")
    @classmethod
    def dates(cls, value: object) -> date | None:
        return canonical_date(value)

    @field_validator("permission_reference")
    @classmethod
    def permission_text(cls, value: str | None) -> str | None:
        return cls.clean_reference(value)

    @field_validator("asking_price", mode="before")
    @classmethod
    def decimal_string(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        if not isinstance(value, str) or not re.fullmatch(r"-?[0-9]{1,12}(?:\.[0-9]{1,2})?", value):
            raise ValueError(
                "cash asking amount must be a finite decimal string with at most two decimals"
            )
        return Decimal(value)


class PricingRequest(APIModel):
    schema_version: Literal["howreliable-pricing-input-1.0"] = "howreliable-pricing-input-1.0"
    comparison_date: date
    subject: PricingSubject
    comparables: tuple[ManualComparable, ...] = Field(max_length=10)

    @field_validator("comparison_date", mode="before")
    @classmethod
    def date_input(cls, value: object) -> date | None:
        return canonical_date(value)

    @field_validator("comparables", mode="before")
    @classmethod
    def array_input(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def consistent_entries(self) -> PricingRequest:
        entries = {r.entry_id: r for r in self.comparables}
        if len(entries) != len(self.comparables):
            raise ValueError("entry IDs must be unique")
        if len({r.permission_basis == "synthetic" for r in self.comparables}) > 1:
            raise ValueError("synthetic and real observations cannot be mixed")
        for row in self.comparables:
            for field in ("duplicate_of_entry_id", "possible_duplicate_of_entry_id"):
                target = getattr(row, field)
                if target is not None and (target not in entries or target == row.entry_id):
                    raise ValueError("duplicate reference must name another submitted entry")
            for field in ("duplicate_of_entry_id", "possible_duplicate_of_entry_id"):
                seen: set[str] = set()
                current: str | None = row.entry_id
                while current is not None:
                    if current in seen:
                        raise ValueError("duplicate reference cycle")
                    seen.add(current)
                    current = getattr(entries[current], field)
        return self


class PricingEntry(APIModel):
    observation: ManualComparable
    eligibility: Literal["PRIMARY_COMPARABLE", "CONTEXTUAL_COMPARABLE", "EXCLUDED"]
    reason_codes: list[str]
    missing_fields: list[str]
    mismatched_fields: list[str]
    warnings: list[str]
    duplicate_group_id: str | None = None
    representative_entry_id: str | None = None
    possible_duplicate_group_id: str | None = None
    price_difference_cad: Decimal | None = None
    odometer_difference_km: Decimal | None = None


class PriceSummary(APIModel):
    primary_count: int
    minimum_cad: Decimal | None
    median_cad: Decimal | None
    maximum_cad: Decimal | None
    median_display_cad: str | None
    median_display_rounded: bool
    subject_difference_from_median_cad: Decimal | None


class PricingResult(APIModel):
    schema_version: Literal["howreliable-pricing-comparison-1.0"] = (
        "howreliable-pricing-comparison-1.0"
    )
    policy_version: Literal["howreliable-manual-comparables-policy-1.0"] = (
        "howreliable-manual-comparables-policy-1.0"
    )
    evidence_kind: Literal["advertised_asking_prices"] = "advertised_asking_prices"
    comparison_date: date
    subject: PricingSubject
    entries: list[PricingEntry]
    counts: dict[str, int]
    display_mode: Literal["NO_PRIMARY_EVIDENCE", "INDIVIDUAL_ONLY", "SELECTED_SAMPLE_SUMMARY"]
    price_summary: PriceSummary
    coverage: dict[str, Any]
    method: dict[str, Any]
    input_sha256: str
    limitations: list[str]
