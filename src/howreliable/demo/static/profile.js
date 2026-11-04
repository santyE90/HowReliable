"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const output = $("profile-results"), button = $("profile-load"), panel = $("profile-panel");
  const codes = new Set(["engine", "transmission", "electrical", "cooling", "suspension", "brakes", "steering", "fuel_system", "hvac", "exhaust", "body", "airbags_restraints", "tires_wheels", "other", "unknown"]);
  let version = 0, controller = null;
  const object = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const string = v => typeof v === "string" && v.length > 0;
  const strings = v => Array.isArray(v) && v.every(string);
  const count = v => Number.isSafeInteger(v) && v >= 0;
  const identity = v => object(v) && string(v.make) && string(v.model) && Number.isInteger(v.year) && v.year >= 1886 && v.year <= 2100;
  const vehicle = v => identity(v) && string(v.id);
  const same = (a, b) => identity(a) && identity(b) && ["make", "model", "year"].every(k => a[k] === b[k]);
  const number = v => v.toLocaleString("en-US");
  const node = (tag, value, cls) => {
    const e = document.createElement(tag);
    if (value !== undefined) e.textContent = String(value);
    if (cls) e.className = cls;
    return e;
  };
  function selection() {
    const controls = [$("make"), $("model"), $("year")];
    if (controls.some(c => c.disabled || !c.value)) return null;
    return {make: controls[0].value, model: controls[1].value, year: Number(controls[2].value)};
  }
  function announce(message, error = false) {
    $("profile-status").textContent = message;
    $("profile-status").classList.toggle("error", error);
  }
  function invalidate() {
    version++; controller?.abort(); controller = null;
    output.replaceChildren(); output.hidden = true;
    panel.setAttribute("aria-busy", "false"); button.disabled = !selection();
    announce(selection() ? "Selection changed. Load the profile for this vehicle." : "Choose make, model and year to load a profile.");
  }
  function validOfficial(s, source) {
    if (!object(s) || s.availability !== "AVAILABLE" || s.reason_code !== "verified_offline_snapshot" || s.applicability_status !== "EXACT_BROAD_COHORT_ONLY" || !string(s.snapshot_scope) || !string(s.snapshot_date) || !object(s.provenance) || !Object.values(s.provenance).every(string) || !/^[a-f0-9]{64}$/.test(s.provenance.serving_database_sha256) || s.provenance.serving_schema_version !== "howreliable-official-evidence-1.0" || s.provenance.matching_policy_version !== "official-exact-nfkc-whitespace-casefold-1.0" || !count(s.unique_record_count) || !count(s.returned_record_count) || !Array.isArray(s.records) || s.records.length > 10 || s.returned_record_count !== s.records.length || s.unique_record_count < s.records.length || s.records_truncated !== (s.unique_record_count > s.records.length) || new Set(s.records.map(r => r?.record_id)).size !== s.records.length) return false;
    const kind = source === "recalls" ? "recall" : "communication";
    if (!s.records.length && s.unique_record_count > 0) return false;
    return s.records.every(r => object(r) && r.kind === kind && string(r.record_id) && string(r.source_identifier) && string(r.title) && strings(r.manufacturer_identifiers) && strings(r.descriptions) && strings(r.consequences) && strings(r.remedies) && Array.isArray(r.components) && r.components.every(c => codes.has(c)) && object(r.dates) && Object.values(r.dates).every(v => Array.isArray(v) && v.every(d => typeof d === "string" && /^\d{4}-\d{2}-\d{2}$/.test(d) && !Number.isNaN(Date.parse(d)) && new Date(d).toISOString().slice(0, 10) === d)) && strings(r.quality_flags) && strings(r.source_artifacts) && count(r.matching_applicability_rows) && r.matching_applicability_rows > 0 && string(r.applicability_note) && (kind === "recall" ? r.communication_type === null && r.original_communication_type === null : string(r.communication_type) && string(r.original_communication_type)));
  }
  function valid(data, request, status) {
    if (!object(data) || !["vehicle-problem-profile-1.0", "vehicle-problem-profile-1.1"].includes(data.schema_version) || data.policy_version !== "howreliable-problem-evidence-policy-1.0" || !same(data.requested_identity, request) || data.supplied_configuration !== null) return false;
    const statuses = {AVAILABLE: [200, "EXACT_COHORT_MATCH"], NO_MATCHING_REPORTS: [200, "NO_MATCHING_REPORTS"], AMBIGUOUS_IDENTITY: [409, "AMBIGUOUS_IDENTITY"], SOURCE_UNAVAILABLE: [503, "SOURCE_UNAVAILABLE"]};
    const expected = statuses[data.profile_status], resolution = data.identity_resolution, applicability = data.applicability;
    if (!expected || expected[0] !== status || !object(resolution) || resolution.status !== expected[1] || !Array.isArray(resolution.candidates) || !resolution.candidates.every(c => vehicle(c) && same(c, request)) || new Set(resolution.candidates.map(c => c.id)).size !== resolution.candidates.length) return false;
    if (!object(applicability) || applicability.cohort_match !== resolution.status || applicability.configuration !== "CONFIGURATION_APPLICABILITY_UNRESOLVED" || applicability.individual_vehicle !== "INDIVIDUAL_VEHICLE_NOT_VERIFIED" || applicability.market !== "US_SOURCE_MARKET_APPLICABILITY_UNRESOLVED" || !strings(applicability.limitations) || !strings(data.limitations)) return false;
    if (!Array.isArray(data.missing_information) || !data.missing_information.every(g => object(g) && string(g.code) && string(g.explanation)) || !Array.isArray(data.component_evidence) || !Array.isArray(data.inspection_questions)) return false;
    const available = data.profile_status === "AVAILABLE", h = data.historical_evidence;
    if (available) {
      if (resolution.candidates.length !== 1 || !object(h) || h.schema_version !== "howreliable-demo-1.0" || !vehicle(h.vehicle) || !same(h.vehicle, request) || h.vehicle.id !== resolution.candidates[0].id || !count(h.source_row_count) || !count(h.unique_report_count) || h.source_row_count < h.unique_report_count || !count(h.missing_report_date_rows) || h.missing_report_date_rows > h.source_row_count || !string(h.timeline_policy) || !string(h.limitation) || !object(h.provenance)) return false;
      const date = v => v === null || (typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v)) && new Date(v).toISOString().slice(0, 10) === v);
      if (!date(h.first_report_date) || !date(h.last_report_date) || (h.first_report_date && h.last_report_date && h.first_report_date > h.last_report_date)) return false;
      if (!Array.isArray(h.components) || new Set(h.components.map(c => c?.category)).size !== h.components.length || !h.components.every(c => object(c) && codes.has(c.category) && count(c.source_row_count) && count(c.unique_report_count) && c.source_row_count >= c.unique_report_count && c.source_row_count <= h.source_row_count && c.unique_report_count <= h.unique_report_count)) return false;
      const ordered = [...h.components].sort((a, b) => b.unique_report_count - a.unique_report_count || (a.category < b.category ? -1 : a.category > b.category ? 1 : 0));
      if (ordered.some((c, i) => c !== h.components[i])) return false;
      if (!Array.isArray(h.timeline) || !h.timeline.every(b => object(b) && (b.month === null || (typeof b.month === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(b.month))) && count(b.unique_report_count) && count(b.source_row_count) && b.source_row_count >= b.unique_report_count) || new Set(h.timeline.map(b => b.month)).size !== h.timeline.length || h.timeline.reduce((n, b) => n + b.unique_report_count, 0) !== h.unique_report_count || h.timeline.reduce((n, b) => n + b.source_row_count, 0) !== h.source_row_count) return false;
      if (data.component_evidence.length !== h.components.length) return false;
    } else if (h !== null || data.component_evidence.length || (data.profile_status === "AMBIGUOUS_IDENTITY" ? resolution.candidates.length < 2 : resolution.candidates.length !== 0)) return false;
    const components = new Map((h?.components || []).map(c => [c.category, c]));
    if (!data.component_evidence.every((a, i) => object(a) && a.category === h.components[i].category && string(a.label) && a.count_reference === a.category && a.denominator_reference === "historical_evidence.unique_report_count" && a.evidence_basis === "documented_structured_component_mapping" && a.rule_id === "profile-evidence.v1.structured_component" && strings(a.question_ids) && string(a.interpretation) && strings(a.limitations))) return false;
    const ids = new Set();
    if (!data.inspection_questions.every(q => {
      if (!object(q) || !string(q.question_id) || ids.has(q.question_id) || !string(q.question_text) || !string(q.rule_id) || !strings(q.limitations)) return false;
      ids.add(q.question_id);
      if (q.evidence_basis === "generic_inspection_guidance") return q.supporting_component === null && q.supporting_unique_report_count === null;
      const c = components.get(q.supporting_component);
      return q.evidence_basis === "structured_component_reports" && c && !["other", "unknown"].includes(q.supporting_component) && c.unique_report_count > 0 && q.supporting_unique_report_count === c.unique_report_count && data.component_evidence.some(a => a.category === q.supporting_component && a.question_ids.includes(q.question_id));
    })) return false;
    if (!data.component_evidence.every(a => a.question_ids.every(id => data.inspection_questions.some(q => q.question_id === id && q.supporting_component === a.category)))) return false;
    // Missing questions must not make a truncated policy response look complete.
    const expectedQuestions = [...components.values()].filter(c => c.unique_report_count > 0 && !["other", "unknown"].includes(c.category)).map(c => `profile.v1.component.${c.category}`);
    expectedQuestions.push("profile.v1.generic.independent_inspection", "profile.v1.generic.service_records");
    if (data.inspection_questions.length !== expectedQuestions.length || data.inspection_questions.some((q, i) => q.question_id !== expectedQuestions[i])) return false;
    const sources = data.source_coverage;
    if (!object(sources)) return false;
    for (const key of ["complaints", "recalls", "manufacturer_communications", "validated_symptoms"]) {
      const s = sources[key];
      if (["recalls", "manufacturer_communications"].includes(key) && s?.availability === "AVAILABLE") {
        if (data.schema_version !== "vehicle-problem-profile-1.1" || !available || !validOfficial(s, key)) return false;
        continue;
      }
      if (!object(s) || !string(s.reason_code) || !string(s.explanation) || !string(s.applicability_status) || s.records !== null || !(s.snapshot_date === null || string(s.snapshot_date)) || !(s.provenance_reference === null || string(s.provenance_reference))) return false;
      if (key === "complaints") {
        if (s.availability !== (data.profile_status === "SOURCE_UNAVAILABLE" ? "SOURCE_UNAVAILABLE" : "AVAILABLE") || s.applicability_status !== resolution.status || s.unique_record_count !== (available ? h.unique_report_count : null) || s.provenance_reference !== (available ? "historical_evidence.provenance" : null)) return false;
      } else if (s.availability !== (key === "validated_symptoms" ? "VALIDATED_EVIDENCE_UNAVAILABLE" : "SOURCE_UNAVAILABLE") || s.unique_record_count !== null) return false;
    }
    return data.schema_version !== "vehicle-problem-profile-1.1" || [sources.recalls, sources.manufacturer_communications].some(s => s.availability === "AVAILABLE");
  }
  function list(parent, values) {
    const ul = node("ul"); values.forEach(value => ul.append(node("li", value))); parent.append(ul);
  }
  function details(parent, title, value) {
    const d = node("details"); d.append(node("summary", title), node("pre", JSON.stringify(value, null, 2))); parent.append(d);
  }
  function officialEntries(parent, source, label) {
    if (source.availability !== "AVAILABLE") return;
    const section = node("details", undefined, "official-evidence");
    const units = label === "NHTSA recalls" ? "campaigns" : "documents";
    section.append(node("summary", `${label} — ${number(source.unique_record_count)} unique ${units} in this snapshot`), node("p", source.snapshot_scope, "muted"), node("p", "U.S. regulatory/documentary records, not failure-frequency measurements. Broad cohort applicability only; verify the individual vehicle independently.", "notice"));
    if (!source.records.length) section.append(node("p", "No exact matching records in this verified snapshot. This is not proof of no recalls, bulletins or problems."));
    if (source.records_truncated) section.append(node("p", `Showing the first ${source.returned_record_count} of ${source.unique_record_count} unique ${units}, ordered by stable NHTSA identity. Additional records remain in the local artifact; this view is not exhaustive.`, "notice"));
    for (const r of source.records) {
      const entry = node("details"); entry.append(node("summary", r.title));
      entry.append(node("p", `NHTSA identity: ${r.source_identifier}. Manufacturer reference: ${r.manufacturer_identifiers.join(", ") || "Not supplied"}.`));
      if (r.original_communication_type) entry.append(node("p", `Source communication type: ${r.original_communication_type}.`));
      for (const [title, values] of [["Source description / summary", r.descriptions], ["Consequence", r.consequences], ["Remedy", r.remedies]]) {
        if (r.kind === "communication" && title !== "Source description / summary") continue;
        entry.append(node("h5", title));
        if (values.length) list(entry, values); else entry.append(node("p", "Not supplied in this snapshot.", "muted"));
      }
      entry.append(node("p", `Campaign/document-wide components: ${r.components.map(c => c.replaceAll("_", " ")).join(", ") || "Not supplied"}. These labels are not specific failure findings for this vehicle.`, "muted"), node("p", r.applicability_note, "muted"));
      details(entry, "Source dates, applicability and traceability", {dates: r.dates, source_artifacts: r.source_artifacts, matching_applicability_rows: r.matching_applicability_rows, quality_flags: r.quality_flags, record_id: r.record_id}); section.append(entry);
    }
    details(section, "Verified source provenance", source.provenance); parent.append(section);
  }
  function render(data) {
    // Assemble off-DOM; a failed render cannot publish partial evidence.
    const body = node("div"), identity = data.historical_evidence?.vehicle || data.requested_identity;
    const title = node("h3", `${identity.year} ${identity.make} ${identity.model}`);
    title.id = "profile-result-title"; title.tabIndex = -1; body.append(title);
    const messages = {
      AVAILABLE: "Exact historical cohort match. Configuration applicability remains unresolved.",
      NO_MATCHING_REPORTS: "No matching complaint cohort was found. This is not a verified zero-report vehicle or proof of safety.",
      AMBIGUOUS_IDENTITY: "Ambiguous cohort identity. No candidate was selected or combined; historical evidence is not displayed.",
      SOURCE_UNAVAILABLE: "Complaint source unavailable. Counts are unknown, not zero. Other dashboard features may remain available."
    };
    body.append(node("p", messages[data.profile_status], "notice"));
    const h = data.historical_evidence;
    if (h) {
      body.append(node("p", `${number(h.unique_report_count)} unique complaint reports · ${number(h.source_row_count)} original source rows (duplicate rows retained).`, "profile-counts"), node("p", `Historical reporting period: ${h.first_report_date || "Unknown"} to ${h.last_report_date || "Unknown"}. Valid row-date extrema, not continuous or lifetime coverage.`, "muted"));
      if (h.unique_report_count === 0) body.append(node("p", "Zero recorded reports in this source do not establish absence of problems or safety.", "notice"));
      body.append(node("h4", "Reported component evidence"), node("p", "Counts are unique reports associated with mapped structured component labels, not verified failures or validated text mentions. Categories overlap; do not sum them. Order is frequency, not severity. Counts are not failure rates.", "muted"));
      const componentDetails = node("details"); componentDetails.append(node("summary", "View component counts and complaint-linked inspection questions"));
      if (!h.components.length) componentDetails.append(node("p", "No structured component evidence is recorded. This does not establish a problem-free vehicle."));
      data.component_evidence.forEach(a => {
        const c = h.components.find(c => c.category === a.category), section = node("section", undefined, "profile-component");
        section.append(node("h5", `${a.label} — ${number(c.unique_report_count)} unique reports`), node("p", a.interpretation, "muted"));
        const questions = data.inspection_questions.filter(q => a.question_ids.includes(q.question_id));
        questions.forEach(q => {
          section.append(node("p", q.question_text), node("p", `Structured component reports · ${number(q.supporting_unique_report_count)} supporting unique reports. Inspection prompt, not diagnosis.`, "muted"));
          details(section, "Question evidence and rule", q);
        });
        if (!questions.length) section.append(node("p", "No specific part-level question is inferred from this category.", "muted"));
        details(section, "Component evidence limitations", a.limitations); componentDetails.append(section);
      }); body.append(componentDetails);
      // Reuse the existing historical charts rather than creating another timeline.
      const coverage = node("details"); coverage.append(node("summary", "Report-date coverage and accounting"), node("p", `${number(h.missing_report_date_rows)} source rows have missing report dates. Unknown or conflicting report dates remain in the unknown-month bucket; see the historical charts when loaded.`, "muted"), node("pre", JSON.stringify({timeline_policy: h.timeline_policy, unknown_month: h.timeline.find(b => b.month === null) || null}, null, 2))); body.append(coverage);
    }
    body.append(node("h4", "General inspection questions — not complaint-linked"));
    list(body, data.inspection_questions.filter(q => q.evidence_basis === "generic_inspection_guidance").map(q => q.question_text));
    body.append(node("h4", "Source availability"));
    const labels = {complaints: "U.S. NHTSA complaints", recalls: "NHTSA recall evidence", manufacturer_communications: "Manufacturer communications / TSBs", validated_symptoms: "Validated NLP symptom evidence"};
    const availability = {AVAILABLE: "Source available", SOURCE_UNAVAILABLE: "Unavailable locally — not zero", VALIDATED_EVIDENCE_UNAVAILABLE: "Unavailable — human validation deferred"};
    list(body, Object.entries(labels).map(([key, label]) => `${label}: ${availability[data.source_coverage[key].availability]}.`));
    officialEntries(body, data.source_coverage.recalls, "NHTSA recalls");
    officialEntries(body, data.source_coverage.manufacturer_communications, "Manufacturer communications / TSBs");
    body.append(node("p", "Exact make/model/year matching does not establish trim or powertrain applicability. Individual VIN and Canadian-market applicability are unverified; no open-recall or remedy-completion check is performed.", "notice"));
    details(body, "Missing evidence and applicability caveats", {applicability: data.applicability, missing_information: data.missing_information});
    const coverageMetadata = Object.fromEntries(Object.entries(data.source_coverage).map(([key, value]) => [key, Object.fromEntries(Object.entries(value).filter(([field]) => field !== "records"))]));
    details(body, "Index version, source coverage and provenance", {schema_version: data.schema_version, policy_version: data.policy_version, historical_provenance: h?.provenance || null, source_coverage: coverageMetadata, identity_resolution: data.identity_resolution});
    details(body, "Full evidence limitations", data.limitations);
    output.replaceChildren(body); output.hidden = false; title.focus();
  }
  button.addEventListener("click", async () => {
    const request = selection();
    invalidate();
    if (!request) {announce("Choose a valid make, model and year first.", true); return;}
    const current = version; controller = new AbortController();
    button.disabled = true; panel.setAttribute("aria-busy", "true");
    announce(`Loading profile for ${request.year} ${request.make} ${request.model}…`);
    try {
      const response = await fetch("/api/demo/v1/vehicle-problem-profiles", {method: "POST", credentials: "omit", cache: "no-store", signal: controller.signal, headers: {"Content-Type": "application/json"}, body: JSON.stringify(request)});
      if (current !== version || !same(request, selection())) return;
      if (![200, 409, 503].includes(response.status)) throw new Error(`Profile request failed (HTTP ${response.status}). Check the local server and selection, then retry.`);
      const raw = await response.text();
      if (raw.length > 4000000) throw new Error("Profile response is too large. No evidence was displayed.");
      const data = JSON.parse(raw);
      if (current !== version || !same(request, selection())) return;
      if (!valid(data, request, response.status)) throw new Error("Profile response is incomplete or does not match this selection. No evidence was displayed.");
      render(data);
      announce(`Profile for ${request.year} ${request.make} ${request.model}: ${data.profile_status === "AVAILABLE" ? "loaded" : data.profile_status === "NO_MATCHING_REPORTS" ? "no matching cohort" : data.profile_status === "AMBIGUOUS_IDENTITY" ? "identity requires resolution" : "source unavailable"}.`, data.profile_status === "SOURCE_UNAVAILABLE");
    } catch (error) {
      if (current === version) {
        output.replaceChildren(); output.hidden = true;
        announce(error instanceof SyntaxError ? "Invalid profile response. No evidence was displayed; retry." : error.name === "AbortError" ? "Profile request cancelled. Load again to retry." : "Profile unavailable. " + error.message, true);
      }
    } finally {
      if (current === version) {controller = null; button.disabled = !selection(); panel.setAttribute("aria-busy", "false");}
    }
  });
  for (const id of ["make", "model", "year"]) for (const event of ["input", "change"]) $(id).addEventListener(event, invalidate);
  $("reset").addEventListener("click", invalidate);
  // Discovery updates disabled options without dispatching input events.
  const observer = new MutationObserver(() => {button.disabled = panel.getAttribute("aria-busy") === "true" || !selection();});
  for (const id of ["make", "model", "year"]) observer.observe($(id), {attributes: true, attributeFilter: ["disabled"], childList: true});
  invalidate();
})();
