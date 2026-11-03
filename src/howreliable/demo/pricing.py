"""Pure manual asking-price comparisons; no retrieval, storage, valuation or P4 inference."""

import hashlib
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from itertools import combinations

from howreliable.demo.pricing_schemas import (
    ManualComparable,
    PriceSummary,
    PricingEntry,
    PricingRequest,
    PricingResult,
)

CONFIG = ("trim", "powertrain", "transmission", "drivetrain", "body_style")
MATCH_FIELDS = (
    *CONFIG,
    "province",
    "seller_type",
    "condition_status",
    "accident_history",
    "title_status",
)


def _groups(ids: list[str], edges: list[tuple[str, str]]) -> dict[str, frozenset[str]]:
    groups = {key: frozenset([key]) for key in ids}
    for a, b in edges:
        joined = groups[a] | groups[b]
        for key in joined:
            groups[key] = joined
    return groups


def _id(members: frozenset[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(members)).encode()).hexdigest()


def _same_reference(a: ManualComparable, b: ManualComparable) -> bool:
    return bool(
        (
            a.source_name
            and a.source_name == b.source_name
            and a.source_listing_id
            and a.source_listing_id == b.source_listing_id
        )
        or (a.listing_url and a.listing_url == b.listing_url)
    )


def _km(row: ManualComparable) -> Decimal | None:
    if row.odometer is None or row.odometer_unit == "unknown":
        return None
    return Decimal(row.odometer) * (Decimal("1.609344") if row.odometer_unit == "mi" else 1)


def compare_prices(request: PricingRequest) -> PricingResult:
    """Input ordering is retained; representative selection and aggregates are order-independent."""
    with localcontext() as context:
        context.prec = max(60, len(format(request.subject.asking_price_cad or 0, "f")) + 20)
        return _compare(request)


def _compare(request: PricingRequest) -> PricingResult:
    rows = {r.entry_id: r for r in request.comparables}
    ids = list(rows)
    edges = [
        (r.entry_id, r.duplicate_of_entry_id)
        for r in rows.values()
        if r.duplicate_of_entry_id is not None
    ]
    edges.extend(
        (a.entry_id, b.entry_id) for a, b in combinations(rows.values(), 2) if _same_reference(a, b)
    )
    groups = _groups(ids, edges)
    uncertain = [
        (r.entry_id, r.possible_duplicate_of_entry_id)
        for r in rows.values()
        if r.possible_duplicate_of_entry_id is not None
    ]
    if any(groups[a] == groups[b] for a, b in uncertain):
        raise ValueError("entries cannot be both confirmed and possible duplicates")
    for a, b in combinations(rows.values(), 2):
        fields = ("make", "model", "year", *CONFIG, "province", "city")
        av = [getattr(a.vehicle, f) for f in fields]
        bv = [getattr(b.vehicle, f) for f in fields]
        if (
            groups[a.entry_id] != groups[b.entry_id]
            and a.source_name != b.source_name
            and all(v not in (None, "unknown", "other") for v in av + bv)
            and av == bv
            and a.odometer is not None
            and a.odometer_unit != "unknown"
            and (a.odometer, a.odometer_unit, a.asking_price)
            == (b.odometer, b.odometer_unit, b.asking_price)
            and a.asking_price is not None
        ):
            uncertain.append((a.entry_id, b.entry_id))
    possible = _groups(ids, edges + uncertain)
    uncertain_members = set().union(*(possible[a] for a, _ in uncertain)) if uncertain else set()
    self_ids: set[str] = set()
    subject = request.subject
    for row in rows.values():
        ref = subject.subject_reference
        same = ref and (
            (ref.listing_url and ref.listing_url == row.listing_url)
            or (
                ref.source_name
                and ref.source_name == row.source_name
                and ref.source_listing_id
                and ref.source_listing_id == row.source_listing_id
            )
        )
        if row.is_subject_vehicle == "yes" or same:
            self_ids.update(groups[row.entry_id])
    representatives = {
        key: min(members, key=lambda k: (-(rows[k].observed_on or date.min).toordinal(), k))
        for key, members in groups.items()
    }
    entries: list[PricingEntry] = []
    for row in rows.values():
        excluded: list[str] = []
        contextual: list[str] = []
        missing: list[str] = []
        mismatched: list[str] = []
        warnings = ["User-entered facts and permission claims are not independently verified."]
        for field in ("source_name", "observed_on", "asking_price", "currency", "price_basis"):
            if getattr(row, field) in (None, "unknown"):
                missing.append(field)
        if (
            not row.permission_attested
            or row.permission_basis == "unknown"
            or (row.permission_basis != "synthetic" and not row.permission_reference)
        ):
            excluded.append("permission_unusable")
        if not row.source_name or row.observed_on is None:
            excluded.append("provenance_missing")
        if row.currency != "CAD":
            excluded.append("currency_not_cad")
        if row.price_basis != "cash_asking":
            excluded.append("not_cash_asking")
        if row.asking_price is None or row.asking_price <= 0:
            excluded.append("price_unusable")
        if (row.observed_on and row.observed_on > request.comparison_date) or (
            row.listed_on and row.observed_on and row.listed_on > row.observed_on
        ):
            excluded.append("date_inconsistent")
        if row.listing_status == "inactive_reported":
            excluded.append("listing_inactive")
        if row.entry_id in self_ids:
            excluded.append("subject_listing")
        if representatives[row.entry_id] != row.entry_id:
            excluded.append("duplicate_listing")
        identity = (row.vehicle.make, row.vehicle.model, row.vehicle.year)
        if None in identity:
            excluded.append("identity_missing")
        elif identity != (subject.make, subject.model, subject.year):
            excluded.append("identity_mismatch")
        if row.entry_id in uncertain_members:
            contextual.append("possible_duplicate")
        if row.is_subject_vehicle == "unknown":
            contextual.append("subject_identity_unconfirmed")
        for field in MATCH_FIELDS:
            actual, expected = getattr(row.vehicle, field), getattr(subject, field)
            if actual in (None, "unknown", "other") or expected in (None, "unknown", "other"):
                missing.append(field)
                contextual.append(f"{field}_unknown")
            elif actual != expected:
                mismatched.append(field)
                contextual.append(f"{field}_mismatch")
        if row.vehicle.title_status in {"salvage", "rebuilt", "other"}:
            contextual.append("title_not_standard")
        if row.tax_fee_basis == "unknown" or subject.tax_fee_basis == "unknown":
            missing.append("tax_fee_basis")
            contextual.append("tax_fee_basis_unknown")
        elif row.tax_fee_basis != subject.tax_fee_basis:
            mismatched.append("tax_fee_basis")
            contextual.append("tax_fee_basis_mismatch")
        km = _km(row)
        delta = (
            km - subject.odometer_km if km is not None and subject.odometer_km is not None else None
        )
        if delta is None:
            missing.append("odometer")
            contextual.append("odometer_unknown")
        elif abs(delta) > 25_000:
            contextual.append("mileage_outside_window")
        if row.observed_on and (request.comparison_date - row.observed_on).days > 30:
            contextual.append("observation_stale")
        if row.listing_status == "unknown":
            contextual.append("listing_status_unknown")
        if not row.vehicle.city or not subject.city:
            warnings.append(
                "City information is incomplete; province matching is not local-market equivalence."
            )
        elif row.vehicle.city != subject.city:
            warnings.append("Cities differ; primary eligibility uses province only.")
        if not row.source_listing_id and not row.listing_url:
            warnings.append("No listing reference; cross-source duplicates may be undetected.")
        if len({rows[k].asking_price for k in groups[row.entry_id]}) > 1:
            warnings.append(
                "Confirmed duplicates have different asking prices; newest observation represents "
                "the group."
            )
        entries.append(
            PricingEntry(
                observation=row,
                eligibility="EXCLUDED"
                if excluded
                else "CONTEXTUAL_COMPARABLE"
                if contextual
                else "PRIMARY_COMPARABLE",
                reason_codes=excluded + contextual or ["exact_identity_and_policy_match"],
                missing_fields=missing,
                mismatched_fields=mismatched,
                warnings=warnings,
                duplicate_group_id=_id(groups[row.entry_id])
                if len(groups[row.entry_id]) > 1
                else None,
                representative_entry_id=representatives[row.entry_id],
                possible_duplicate_group_id=_id(possible[row.entry_id])
                if row.entry_id in uncertain_members
                else None,
                price_difference_cad=(
                    row.asking_price - subject.asking_price_cad
                    if not excluded
                    and row.asking_price is not None
                    and subject.asking_price_cad is not None
                    and subject.asking_price_cad > 0
                    else None
                ),
                odometer_difference_km=delta if not excluded else None,
            )
        )
    primary = [e.observation for e in entries if e.eligibility == "PRIMARY_COMPARABLE"]
    prices = sorted(r.asking_price for r in primary if r.asking_price is not None)
    n = len(prices)
    median = (
        (prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2) if n >= 3 else None
    )
    rounded = (
        median.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if median is not None else None
    )
    kilometres = [km for row in primary if (km := _km(row)) is not None]
    dates = [r.observed_on for r in primary if r.observed_on is not None]
    contextual_count = sum(e.eligibility == "CONTEXTUAL_COMPARABLE" for e in entries)
    payload = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return PricingResult(
        comparison_date=request.comparison_date,
        subject=subject,
        entries=entries,
        counts={
            "submitted": len(entries),
            "primary": n,
            "contextual": contextual_count,
            "excluded": len(entries) - n - contextual_count,
            "eligible": n + contextual_count,
            "confirmed_duplicate_groups": len({g for g in groups.values() if len(g) > 1}),
            "unresolved_duplicate_groups": len({possible[k] for k in uncertain_members}),
        },
        display_mode="NO_PRIMARY_EVIDENCE"
        if not n
        else "INDIVIDUAL_ONLY"
        if n < 3
        else "SELECTED_SAMPLE_SUMMARY",
        price_summary=PriceSummary(
            primary_count=n,
            minimum_cad=prices[0] if n else None,
            maximum_cad=prices[-1] if n else None,
            median_cad=median,
            median_display_cad=format(rounded, ".2f") if rounded is not None else None,
            median_display_rounded=median != rounded,
            subject_difference_from_median_cad=(
                subject.asking_price_cad - median
                if median is not None
                and subject.asking_price_cad is not None
                and subject.asking_price_cad > 0
                else None
            ),
        ),
        coverage={
            "primary_minimum_km": min(kilometres) if kilometres else None,
            "primary_maximum_km": max(kilometres) if kilometres else None,
            "primary_observed_from": min(dates) if dates else None,
            "primary_observed_to": max(dates) if dates else None,
            "primary_cities": sorted({r.vehicle.city for r in primary if r.vehicle.city}),
            "primary_provinces": sorted(
                {r.vehicle.province for r in primary if r.vehicle.province}
            ),
            "primary_seller_types": sorted({r.vehicle.seller_type for r in primary}),
            "permission_statuses": sorted({r.permission_basis for r in rows.values()}),
            "verification_statuses": sorted({r.verification_status for r in rows.values()}),
            "subject_price_status": "usable"
            if subject.asking_price_cad is not None and subject.asking_price_cad > 0
            else "unavailable",
            "gaps": sorted({g for e in entries for g in e.missing_fields}),
            "mismatches": sorted({g for e in entries for g in e.mismatched_fields}),
            "summary_status": "No primary evidence"
            if not n
            else "Median requires three primary listings"
            if n < 3
            else "Selected advertised sample only",
        },
        method={
            "maximum_comparables": 10,
            "maximum_mileage_difference_km": 25_000,
            "maximum_observation_age_days": 30,
            "region_match": "province; cities disclosed",
            "rounding": "ROUND_HALF_UP; exact Decimal calculations retained",
            "price_difference_sign": "comparable minus subject",
            "median_difference_sign": "subject minus selected-sample median",
            "duplicate_representative": "latest observed date then lexical entry ID",
        },
        input_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        limitations=[
            "Selected advertised asking prices, not completed transactions or fair market value.",
            "No claim that this sample represents the Canadian market; selection bias remains.",
            "Source facts, permissions, condition and history are user-entered and unverified.",
            "Mileage and freshness guards are product heuristics, not validated market standards.",
            "No depreciation, mileage-price, repair-cost or accident-discount adjustments.",
            "Hidden duplicates, stale observations and different local markets can remain.",
            "Pricing does not change P4 purchase readiness, mechanical concerns, ML or NLP.",
        ],
    )
