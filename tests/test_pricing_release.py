"""P5E synthetic arithmetic, sensitivity, permissions and release invariants."""

import io
import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from howreliable.demo.app import create_app
from howreliable.demo.index import build_index
from howreliable.demo.pricing import compare_prices
from howreliable.demo.pricing_schemas import PricingRequest
from test_demo_history import TIME, record, source_file
from test_pricing import listing, payload


@pytest.mark.parametrize("make,model", [("BMW", "335i"), ("Toyota", "Corolla")])
@pytest.mark.parametrize("n", [0, 1, 2, 3, 10])
def test_cohorts_and_sample_sizes(make: str, model: str, n: int) -> None:
    rows = [listing(str(i), str(10000 + i * 100)) for i in range(n)]
    data = payload(rows)
    subject = data["subject"]
    assert isinstance(subject, dict)
    subject.update(make=make, model=model)
    for row in rows:
        vehicle = row["vehicle"]
        assert isinstance(vehicle, dict)
        vehicle.update(make=make, model=model)
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(data)))
    assert result.counts["primary"] == n
    expected = Decimal(10000) + Decimal(n - 1) * 50 if n >= 3 else None
    assert result.price_summary.median_cad == expected


@pytest.mark.parametrize(
    "offset,primary",
    [(24999, True), (25000, True), (25001, False), (-24999, True), (-25000, True), (-25001, False)],
)
def test_two_sided_mileage_boundary(offset: int, primary: bool) -> None:
    request = PricingRequest.model_validate_json(
        json.dumps(
            payload(
                [
                    listing(odometer=200000 + offset),
                ]
            )
        )
    )
    assert compare_prices(request).counts["primary"] == int(primary)


@pytest.mark.parametrize("age,primary", [(29, True), (30, True), (31, False)])
def test_freshness_boundary(age: int, primary: bool) -> None:
    observed = (date(2026, 11, 3) - timedelta(days=age)).isoformat()
    result = compare_prices(
        PricingRequest.model_validate_json(
            json.dumps(
                payload(
                    [
                        listing(observed_on=observed),
                    ]
                )
            )
        )
    )
    assert result.counts["primary"] == int(primary)


@pytest.mark.parametrize(
    "subject_price,difference", [("11000.00", "-1000"), ("12000", "0"), ("13000", "1000")]
)
def test_price_difference_direction(subject_price: str, difference: str) -> None:
    data = payload([listing("a", "11000"), listing("b", "12000"), listing("c", "13000")])
    subject = data["subject"]
    assert isinstance(subject, dict)
    subject["asking_price_cad"] = subject_price
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(data)))
    assert result.price_summary.subject_difference_from_median_cad == Decimal(difference)
    assert result.entries[0].price_difference_cad == Decimal(11000) - Decimal(subject_price)


def test_extreme_price_and_category_sensitivity() -> None:
    rows = [listing("a", "11000"), listing("b", "12000"), listing("c", "13000")]
    initial = compare_prices(PricingRequest.model_validate_json(json.dumps(payload(rows))))
    rows.append(listing("d", "999999999999.99"))
    changed = compare_prices(PricingRequest.model_validate_json(json.dumps(payload(rows))))
    assert changed.price_summary.median_cad == Decimal(12500)
    assert changed.price_summary.maximum_cad == Decimal("999999999999.99")
    rows[-1]["odometer"] = 225001
    contextual = compare_prices(PricingRequest.model_validate_json(json.dumps(payload(rows))))
    assert contextual.price_summary == initial.price_summary
    rows[-1]["permission_attested"] = False
    excluded = compare_prices(PricingRequest.model_validate_json(json.dumps(payload(rows))))
    assert excluded.price_summary == initial.price_summary
    assert excluded.counts["excluded"] == 1
    assert excluded.coverage["primary_seller_types"] == ["dealer"]
    assert any("selection bias" in text.lower() for text in excluded.limitations)


def test_small_even_money_and_permissions_revocation() -> None:
    rows = [listing(str(i), value) for i, value in enumerate(["0.01", "0.01", "0.02", "0.02"])]
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(payload(rows))))
    assert result.price_summary.median_cad == Decimal("0.015")
    assert result.price_summary.median_display_cad == "0.02"
    for row in rows:
        row["permission_attested"] = False
    revoked = compare_prices(PricingRequest.model_validate_json(json.dumps(payload(rows))))
    assert revoked.counts["excluded"] == 4
    assert revoked.price_summary.median_cad is None


@pytest.mark.parametrize(
    "field,value,category",
    [
        ("trim", None, "contextual"),
        ("province", "QC", "contextual"),
        ("powertrain", "diesel", "contextual"),
    ],
)
def test_all_contextual_samples(field: str, value: object, category: str) -> None:
    rows = [listing(str(i), str(10000 + i * 100)) for i in range(3)]
    for row in rows:
        vehicle = row["vehicle"]
        assert isinstance(vehicle, dict)
        vehicle[field] = value
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(payload(rows))))
    assert result.counts[category] == 3 and result.price_summary.median_cad is None


def test_no_listing_facts_in_success_or_validation_logs(tmp_path: Path) -> None:
    index = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, [record()]), index, TIME)
    client = TestClient(create_app(root=tmp_path, index_path=index))
    capture = io.StringIO()
    handler = logging.StreamHandler(capture)
    logger = logging.getLogger("howreliable.api")
    logger.addHandler(handler)
    marker = "PRIVATE_SYNTHETIC_SOURCE_MARKER"
    try:
        data = payload([listing(source_name=marker, permission_reference=marker)])
        assert client.post("/api/demo/v1/price-comparisons", json=data).status_code == 200
        data = payload([listing(source_name=marker, price="invalid amount")])
        assert client.post("/api/demo/v1/price-comparisons", json=data).status_code == 422
    finally:
        logger.removeHandler(handler)
    assert "API request completed" in capture.getvalue()
    assert marker not in capture.getvalue()
    assert "invalid amount" not in capture.getvalue()
