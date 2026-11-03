"""Synthetic asking-price evidence only; no listing retrieval or market-data fixtures."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from howreliable.demo.app import create_app
from howreliable.demo.index import build_index
from howreliable.demo.pricing import compare_prices
from howreliable.demo.pricing_schemas import PricingRequest
from test_demo_history import TIME, record, source_file


def vehicle(**changes: object) -> dict[str, object]:
    return dict(
        make="BMW",
        model="335i",
        year=2011,
        trim="base",
        powertrain="3.0 petrol",
        transmission="automatic",
        drivetrain="rwd",
        body_style="sedan",
        province="ON",
        city="Toronto",
        seller_type="dealer",
        condition_status="no_known_issues_reported",
        accident_history="no",
        title_status="normal_reported",
        **changes,
    )


def listing(key: str = "a", price: object = "11000.00", **changes: object) -> dict[str, object]:
    return {
        "entry_id": key,
        "source_name": "Synthetic dealer",
        "source_listing_id": key,
        "vehicle": vehicle(),
        "odometer": 200000,
        "odometer_unit": "km",
        "asking_price": price,
        "currency": "CAD",
        "price_basis": "cash_asking",
        "tax_fee_basis": "taxes_and_fees_excluded",
        "observed_on": "2026-11-03",
        "listing_status": "active_reported",
        "permission_basis": "synthetic",
        "permission_attested": True,
        "is_subject_vehicle": "no",
        **changes,
    }


def payload(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "comparison_date": "2026-11-03",
        "subject": {
            **vehicle(),
            "odometer_km": 200000,
            "asking_price_cad": "12000.00",
            "tax_fee_basis": "taxes_and_fees_excluded",
        },
        "comparables": rows,
    }


@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_sparse_samples_and_accounting(n: int) -> None:
    result = compare_prices(
        PricingRequest.model_validate_json(
            json.dumps(payload([listing(str(i), str(11000 + i * 1000)) for i in range(n)]))
        )
    )
    assert result.counts["submitted"] == n == result.counts["primary"]
    assert result.price_summary.minimum_cad == (Decimal(11000) if n else None)
    assert result.price_summary.median_cad == (Decimal(12000) if n == 3 else None)
    assert result.display_mode == (
        "NO_PRIMARY_EVIDENCE"
        if n == 0
        else "INDIVIDUAL_ONLY"
        if n < 3
        else "SELECTED_SAMPLE_SUMMARY"
    )


@pytest.mark.parametrize(
    "changes,category,reason",
    [
        ({"odometer": 225000}, "PRIMARY_COMPARABLE", "exact_identity_and_policy_match"),
        ({"odometer": 225001}, "CONTEXTUAL_COMPARABLE", "mileage_outside_window"),
        ({"observed_on": "2026-10-04"}, "PRIMARY_COMPARABLE", "exact_identity_and_policy_match"),
        ({"observed_on": "2026-10-03"}, "CONTEXTUAL_COMPARABLE", "observation_stale"),
        ({"observed_on": "2026-11-04"}, "EXCLUDED", "date_inconsistent"),
        ({"observed_on": None}, "EXCLUDED", "provenance_missing"),
        ({"listed_on": "2026-11-04"}, "EXCLUDED", "date_inconsistent"),
        ({"odometer": None}, "CONTEXTUAL_COMPARABLE", "odometer_unknown"),
        ({"permission_attested": False}, "EXCLUDED", "permission_unusable"),
        ({"permission_basis": "unknown"}, "EXCLUDED", "permission_unusable"),
        ({"permission_basis": "licensed"}, "EXCLUDED", "permission_unusable"),
        ({"source_name": None}, "EXCLUDED", "provenance_missing"),
        ({"currency": "USD"}, "EXCLUDED", "currency_not_cad"),
        ({"price_basis": "monthly_payment"}, "EXCLUDED", "not_cash_asking"),
        ({"price_basis": "valuation"}, "EXCLUDED", "not_cash_asking"),
        ({"price_basis": "transaction"}, "EXCLUDED", "not_cash_asking"),
        ({"asking_price": "0"}, "EXCLUDED", "price_unusable"),
        ({"asking_price": "-1"}, "EXCLUDED", "price_unusable"),
        ({"asking_price": None}, "EXCLUDED", "price_unusable"),
        ({"is_subject_vehicle": "yes"}, "EXCLUDED", "subject_listing"),
        (
            {"is_subject_vehicle": "unknown"},
            "CONTEXTUAL_COMPARABLE",
            "subject_identity_unconfirmed",
        ),
    ],
)
def test_eligibility(changes: dict[str, object], category: str, reason: str) -> None:
    row = listing()
    row.update(changes)
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(payload([row]))))
    assert result.entries[0].eligibility == category
    assert reason in result.entries[0].reason_codes


@pytest.mark.parametrize(
    "field,value,category",
    [
        ("make", None, "EXCLUDED"),
        ("model", "corolla", "EXCLUDED"),
        ("year", 2012, "EXCLUDED"),
        ("province", "QC", "CONTEXTUAL_COMPARABLE"),
        ("trim", None, "CONTEXTUAL_COMPARABLE"),
        ("powertrain", "diesel", "CONTEXTUAL_COMPARABLE"),
        ("transmission", "unknown", "CONTEXTUAL_COMPARABLE"),
        ("drivetrain", "awd", "CONTEXTUAL_COMPARABLE"),
        ("body_style", "coupe", "CONTEXTUAL_COMPARABLE"),
        ("city", "Ottawa", "PRIMARY_COMPARABLE"),
        ("accident_history", "yes", "CONTEXTUAL_COMPARABLE"),
    ],
)
def test_vehicle_matching(field: str, value: object, category: str) -> None:
    v = vehicle()
    v[field] = value
    result = compare_prices(
        PricingRequest.model_validate_json(json.dumps(payload([listing(vehicle=v)])))
    )
    assert result.entries[0].eligibility == category
    if field == "city":
        assert any("Cities differ" in w for w in result.entries[0].warnings)


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "1e3", "1.001", "12,000", 12000, True])
def test_invalid_decimal_inputs(amount: object) -> None:
    with pytest.raises(ValidationError):
        PricingRequest.model_validate_json(json.dumps(payload([listing(price=amount)])))


def test_decimal_rounding_units_and_determinism() -> None:
    request = PricingRequest.model_validate_json(
        json.dumps(
            payload(
                [
                    listing("a", "10000"),
                    listing("b", "11000"),
                    listing("c", "11000.01"),
                    listing("d", "14000", odometer=124274, odometer_unit="mi"),
                ]
            )
        )
    )
    result = compare_prices(request)
    assert result.price_summary.median_cad == Decimal("11000.005")
    assert result.price_summary.median_display_cad == "11000.01"
    assert result.price_summary.median_display_rounded
    assert result.price_summary.subject_difference_from_median_cad == Decimal("999.995")
    assert result.entries[0].price_difference_cad == Decimal("-2000")
    assert (
        result.entries[3].odometer_difference_km == Decimal(124274) * Decimal("1.609344") - 200000
    )
    assert result.model_dump_json() == compare_prices(request).model_dump_json()


def test_duplicates_newest_selection_and_uncertainty() -> None:
    data = payload(
        [
            listing("a", observed_on="2026-11-02"),
            listing("b", "13000", source_name="Other", duplicate_of_entry_id="a"),
        ]
    )
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(data)))
    assert result.entries[0].eligibility == "EXCLUDED"
    assert result.entries[1].eligibility == "PRIMARY_COMPARABLE"
    assert result.entries[0].representative_entry_id == "b"
    assert result.counts["confirmed_duplicate_groups"] == 1
    assert result.price_summary.minimum_cad == Decimal(13000)
    submitted = data["comparables"]
    assert isinstance(submitted, list)
    data["comparables"] = list(reversed(submitted))
    reverse = compare_prices(PricingRequest.model_validate_json(json.dumps(data)))
    assert reverse.price_summary == result.price_summary
    assert {e.observation.entry_id: e for e in reverse.entries} == {
        e.observation.entry_id: e for e in result.entries
    }
    uncertain = compare_prices(
        PricingRequest.model_validate_json(
            json.dumps(payload([listing("a"), listing("b", source_name="Other")]))
        )
    )
    assert uncertain.counts["primary"] == 0
    assert uncertain.counts["contextual"] == 2
    assert uncertain.counts["unresolved_duplicate_groups"] == 1


def test_exact_references_self_and_invalid_links() -> None:
    data = payload([listing("a"), listing("b", source_listing_id="a")])
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(data)))
    assert result.counts["excluded"] == 1
    subject = data["subject"]
    assert isinstance(subject, dict)
    subject["subject_reference"] = {"source_name": "Synthetic dealer", "source_listing_id": "a"}
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(data)))
    assert all("subject_listing" in e.reason_codes for e in result.entries)
    for rows in [
        [listing("a", duplicate_of_entry_id="missing")],
        [listing("a", duplicate_of_entry_id="b"), listing("b", duplicate_of_entry_id="a")],
        [listing("a"), listing("a")],
    ]:
        with pytest.raises(ValidationError):
            PricingRequest.model_validate_json(json.dumps(payload(rows)))


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "http://localhost/a",
        "file:///tmp/a",
        "https://x.example/a?token=private",
        "https://u:p@x.example/a",
    ],
)
def test_bad_url_references(url: str) -> None:
    with pytest.raises(ValidationError):
        PricingRequest.model_validate_json(json.dumps(payload([listing(listing_url=url)])))


def test_http_no_store_and_p4_unchanged(tmp_path: Path) -> None:
    index = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, [record()]), index, TIME)
    client = TestClient(create_app(root=tmp_path, index_path=index))
    p4 = {"make": "mazda", "model": "mazda3", "year": 2020}
    before = client.post("/api/demo/v1/purchase-assessments", json=p4).content
    response = client.post("/api/demo/v1/price-comparisons", json=payload([listing()]))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["price_summary"]["minimum_cad"] == "11000.00"
    invalid = client.post("/api/demo/v1/price-comparisons", json=payload([listing(price="NaN")]))
    assert invalid.status_code == 422 and invalid.headers["cache-control"] == "no-store"
    assert client.post("/api/demo/v1/purchase-assessments", json=p4).content == before


def test_newest_unusable_duplicate_does_not_fall_back() -> None:
    result = compare_prices(
        PricingRequest.model_validate_json(
            json.dumps(
                payload(
                    [
                        listing("old", observed_on="2026-11-02"),
                        listing("new", price=None, duplicate_of_entry_id="old"),
                    ]
                )
            )
        )
    )
    assert result.counts["primary"] == 0
    assert all(e.eligibility == "EXCLUDED" for e in result.entries)
    assert all(e.representative_entry_id == "new" for e in result.entries)


def test_explicit_possible_duplicate_and_contradiction() -> None:
    rows = [listing("a"), listing("b", "13000", possible_duplicate_of_entry_id="a")]
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(payload(rows))))
    assert result.counts["contextual"] == 2
    rows[1]["duplicate_of_entry_id"] = "a"
    request = PricingRequest.model_validate_json(json.dumps(payload(rows)))
    with pytest.raises(ValueError, match="both confirmed and possible"):
        compare_prices(request)


def test_inert_url_normalization_and_exact_duplicates() -> None:
    request = PricingRequest.model_validate_json(
        json.dumps(
            payload(
                [
                    listing("a", listing_url="https://PUBLIC.example:443/Ad"),
                    listing("b", listing_url="https://public.example/Ad"),
                ]
            )
        )
    )
    assert request.comparables[0].listing_url == "https://public.example/Ad"
    result = compare_prices(request)
    assert result.counts["primary"] == 1
    assert result.counts["excluded"] == 1


def test_real_permission_basis_and_synthetic_mixing() -> None:
    real = listing(
        permission_basis="explicit_permission", permission_reference="Owner consent reference"
    )
    request = PricingRequest.model_validate_json(json.dumps(payload([real])))
    assert compare_prices(request).counts["primary"] == 1
    with pytest.raises(ValidationError, match="cannot be mixed"):
        PricingRequest.model_validate_json(json.dumps(payload([real, listing("b")])))


def test_missing_subject_price_and_unknown_configuration() -> None:
    data = payload([listing()])
    subject = data["subject"]
    assert isinstance(subject, dict)
    subject["asking_price_cad"] = None
    result = compare_prices(PricingRequest.model_validate_json(json.dumps(data)))
    assert result.entries[0].price_difference_cad is None
    assert result.price_summary.subject_difference_from_median_cad is None
    subject["trim"] = None
    assert (
        compare_prices(PricingRequest.model_validate_json(json.dumps(data))).counts["contextual"]
        == 1
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"comparison_date": "20261103"},
        {"comparison_date": 1730592000},
        {"comparables": [listing(str(i)) for i in range(11)]},
        {"comparables": [listing(source_name="x" * 101)]},
        {"comparables": [listing(vehicle={**vehicle(), "trim": "\u0000bad"})]},
    ],
)
def test_envelope_validation(changes: dict[str, object]) -> None:
    data = payload([listing()])
    data.update(changes)
    with pytest.raises(ValidationError):
        PricingRequest.model_validate_json(json.dumps(data))
