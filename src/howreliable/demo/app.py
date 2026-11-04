"""Optional local demo factory, preserving the original frozen API factory."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from howreliable.api.app import create_app as create_prediction_app
from howreliable.api.schemas import CohortSummary
from howreliable.api.service import PredictionService
from howreliable.config.settings import Settings
from howreliable.data.ingestion.nhtsa_complaints import sha256_file
from howreliable.demo.index import DEFAULT_INDEX, HistoricalIndex
from howreliable.demo.official_evidence import DEFAULT_OFFICIAL, optional_official
from howreliable.demo.pricing import compare_prices
from howreliable.demo.pricing_schemas import PricingRequest, PricingResult
from howreliable.demo.problem_profile import ProblemProfileService
from howreliable.demo.profile_schemas import ProfileRequest, VehicleProblemProfile
from howreliable.demo.purchase import (
    PurchaseAssessmentService,
    PurchaseVehicleAmbiguousError,
    PurchaseVehicleNotFoundError,
)
from howreliable.demo.purchase_schemas import PurchaseAssessment, PurchaseAssessmentRequest
from howreliable.demo.schemas import (
    ExploratorySummary,
    HistoricalSummary,
    HistoricalVehicle,
    PredictionLink,
    Resolution,
    VehiclePage,
)

G1_SUMMARY = Path("artifacts/nlp/owner-reports/g1-smoke-20261027-seed-8a01/summary.json")


def create_app(
    *, root: Path | None = None, index_path: Path | None = None,
    service: PredictionService | None = None, official_path: Path | None = None,
) -> FastAPI:
    """Local backend only: never select the optional S3 artifact backend."""
    root = root or Path.cwd()
    index = HistoricalIndex(index_path or root / DEFAULT_INDEX)
    app = create_prediction_app(
        root=root, service=service, settings=Settings(artifact_backend="local"),
        allow_model_unavailable=True,
    )
    predictions: PredictionService | None = app.state.prediction_service
    purchase_service = PurchaseAssessmentService(index)
    profile_service = ProblemProfileService(
        index, optional_official(official_path or root / DEFAULT_OFFICIAL),
    )

    @app.post(
        "/api/demo/v1/vehicle-problem-profiles", response_model=VehicleProblemProfile,
        responses={409: {"model": VehicleProblemProfile}, 503: {"model": VehicleProblemProfile}},
    )
    def vehicle_problem_profile(
        request: ProfileRequest, response: Response,
    ) -> VehicleProblemProfile:
        profile = profile_service.profile(request)
        response.status_code = {
            "AMBIGUOUS_IDENTITY": 409, "SOURCE_UNAVAILABLE": 503,
        }.get(profile.profile_status, 200)
        return profile

    @app.middleware("http")
    async def pricing_no_store(
        request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if request.url.path == "/api/demo/v1/price-comparisons":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/demo/v1/price-comparisons", response_model=PricingResult)
    def price_comparison(request: PricingRequest) -> PricingResult:
        try:
            return compare_prices(request)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.post("/api/demo/v1/purchase-assessments", response_model=PurchaseAssessment)
    def purchase_assessment(request: PurchaseAssessmentRequest) -> PurchaseAssessment:
        try:
            return purchase_service.assess(request)
        except PurchaseVehicleNotFoundError as error:
            raise HTTPException(404, "no exact historical vehicle match") from error
        except PurchaseVehicleAmbiguousError as error:
            raise HTTPException(
                409, "ambiguous historical vehicle identity; no match guessed",
            ) from error

    static = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static), name="demo-static")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(static / "index.html", headers={
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        })
    # Reuse the public discovery contract; no feature or model reconstruction.
    cohorts: list[CohortSummary] = []
    offset = 0
    while predictions is not None:
        page = predictions.list_cohorts(limit=100, offset=offset)
        cohorts.extend(page.items)
        offset += len(page.items)
        if offset >= page.total:
            break

    @app.get("/api/demo/v1/vehicles", response_model=VehiclePage)
    def vehicles(
        make: str | None = Query(default=None, min_length=1),
        model: str | None = Query(default=None, min_length=1),
        year: int | None = Query(default=None, ge=1886, le=2100),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> VehiclePage:
        try:
            found = index.discover(make, model, year)
        except ValueError as error:
            raise HTTPException(422, "invalid dependent vehicle filters") from error
        return VehiclePage(
            items=[HistoricalVehicle(**v) for v in found[offset:offset + limit]],
            total=len(found), limit=limit, offset=offset,
            makes=sorted({v["make"] for v in found}),
            models=sorted({v["model"] for v in found}) if make else [],
            years=sorted({v["year"] for v in found}) if model else [],
        )

    @app.get("/api/demo/v1/vehicles/resolve", response_model=Resolution)
    def resolve(make: str, model: str, year: int = Query(ge=1886, le=2100)) -> Resolution:
        try:
            candidates = [HistoricalVehicle(**v) for v in index.discover(make, model, year)]
        except ValueError as error:
            raise HTTPException(422, "invalid vehicle identity") from error
        return Resolution(
            status="unmatched" if not candidates else "matched" if len(candidates) == 1
            else "ambiguous", candidates=candidates,
        )

    @app.get("/api/demo/v1/vehicles/{vehicle_id}/history", response_model=HistoricalSummary)
    def history(vehicle_id: str) -> HistoricalSummary:
        try:
            return HistoricalSummary(**index.summary(vehicle_id))
        except KeyError as error:
            raise HTTPException(404, "historical vehicle not found") from error

    @app.get("/api/demo/v1/vehicles/{vehicle_id}/prediction", response_model=PredictionLink)
    def prediction_link(vehicle_id: str) -> PredictionLink:
        try:
            vehicle = index.summary(vehicle_id)["vehicle"]
        except KeyError as error:
            raise HTTPException(404, "historical vehicle not found") from error
        if predictions is None:
            raise HTTPException(503, detail={
                "code": "MODEL_UNAVAILABLE",
                "message": "Frozen model unavailable; purchase assessment and history "
                "are available.",
            })
        matches = sorted(c.cohort_id for c in cohorts if (
            c.make, c.model, c.model_year
        ) == (vehicle["make"], vehicle["model"], vehicle["year"]))
        # Never silently resolve an identity mismatch by make/model/year alone.
        if matches == [vehicle_id]:
            return PredictionLink(status="supported", cohort_ids=matches,
                                  prediction_url=f"/api/v1/cohorts/{vehicle_id}")
        return PredictionLink(status="ambiguous" if matches else "unsupported",
                              cohort_ids=matches, prediction_url=None)

    @app.get("/api/demo/v1/nlp/sample-summary", response_model=ExploratorySummary)
    def sample_summary() -> ExploratorySummary:
        path = root / G1_SUMMARY
        marker = path.with_suffix(".json.provenance.json")
        if not path.is_file() or not marker.is_file():
            raise HTTPException(503, "bounded NLP summary unavailable")
        provenance = json.loads(marker.read_text(encoding="utf-8"))
        if provenance.get("complete") is not True or (
            provenance.get("output_sha256") != sha256_file(path)
        ):
            raise HTTPException(503, "bounded NLP summary failed verification")
        return ExploratorySummary(summary=json.loads(path.read_text(encoding="utf-8")),
                                  provenance=provenance)

    return app
