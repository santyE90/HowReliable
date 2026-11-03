"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const make = $("make"), model = $("model"), year = $("year");
  const contextControls = [...document.querySelectorAll("[data-context]")];
  const contextLabel = key => $(key)?.labels?.[0]?.textContent || String(key).replaceAll("_", " ");
  const outcomeLabels = {
    INSUFFICIENT_INFORMATION: "Insufficient information",
    PROCEED_WITH_CAUTION: "Proceed with caution",
    WORTH_CONSIDERING: "Worth considering",
    NOT_RECOMMENDED_UNDER_CURRENT_CONDITIONS: "Not recommended under current conditions"
  };
  const originLabels = {
    user_supplied_condition: "User-supplied condition statement",
    user_entered_inspection: "Inspection information entered by the user",
    generic_purchase_guidance: "Generic purchase-process guidance"
  };
  const number = value => Number(value).toLocaleString("en-US");
  // Presentation labels only; canonical category codes and analytics remain unchanged.
  const componentLabels = {
    airbags_restraints: "Airbags & restraints", tires_wheels: "Tires & wheels",
    fuel_system: "Fuel system", hvac: "Heating & air conditioning",
    body: "Body & doors", other: "Other components", unknown: "Unknown / unspecified"
  };
  const componentLabel = code => componentLabels[code] || String(code).replaceAll("_", " ").replace(/^./, c => c.toUpperCase());
  const experimentTitle = "Historical ML Experiment — 2023 Complaint Activity";
  let selectionVersion = 0;
  let resultVersion = 0;
  function node(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = String(text);
    if (cls) e.className = cls;
    return e;
  }
  async function api(path, options = {}) {
    const response = await fetch(path, {...options, credentials: "omit"});
    if (!response.ok) {
      const reason = {404: "No exact historical vehicle match was found.", 409: "The vehicle identity is ambiguous; no match was guessed.", 422: "Check the vehicle and purchase inputs; the server rejected an invalid value.", 503: "This feature is unavailable. Historical evidence and purchase assessments may still be available."}[response.status] || "Check the local server and try again.";
      throw new Error(`Local API request failed (HTTP ${response.status}). ${reason}`);
    }
    return response.json();
  }
  function options(select, values, placeholder) {
    select.replaceChildren(new Option(placeholder, ""), ...values.map(v => new Option(String(v), String(v))));
    select.disabled = values.length === 0;
  }
  function status(text, error = false) {
    $("search-status").textContent = text;
    $("search-status").classList.toggle("error", error);
  }
  function clearResults() {
    resultVersion++;
    $("results").hidden = true;
    $("assessment").replaceChildren(); $("history").replaceChildren(); $("prediction").replaceChildren();
    $("submit").disabled = !year.value;
  }
  async function discover(level) {
    const version = ++selectionVersion;
    clearResults(); $("retry").hidden = true;
    $("submit").disabled = true;
    if (level === "make") options(make, [], "Loading makes…");
    options(year, [], "Choose a model first");
    if (level !== "year") options(model, [], "Choose a make first");
    if (level !== "make" && !make.value) {status("Choose a make to begin."); return;}
    if (level === "year" && !model.value) {status("Choose a model."); return;}
    status("Loading vehicle options…");
    const q = new URLSearchParams({limit: "1"});
    if (level !== "make") q.set("make", make.value);
    if (level === "year") q.set("model", model.value);
    try {
      const page = await api(`/api/demo/v1/vehicles?${q}`);
      if (version !== selectionVersion) return;
      const values = level === "make" ? page.makes : level === "model" ? page.models : page.years;
      options(level === "make" ? make : level === "model" ? model : year, values,
        level === "make" ? "Select make" : level === "model" ? "Select model" : "Select year");
      status(values.length ? "Choose make, model, and year to explore historical reports." : "No matching vehicles are available for this selection.");
    } catch (error) {
      if (version !== selectionVersion) return;
      status(error.message, true); $("retry").hidden = false;
    }
  }
  function metadata(parent, title, value) {
    const details = node("details"), summary = node("summary", title), pre = node("pre", JSON.stringify(value, null, 2));
    details.append(summary, pre); parent.append(details);
  }
  function bars(parent, title, rows) {
    parent.append(node("h3", title));
    if (!rows.length) {parent.append(node("p", "No reported data available.", "muted")); return;}
    const chart = node("div", undefined, "chart"); chart.setAttribute("role", "list");
    const maximum = Math.max(1, ...rows.map(r => r.value));
    rows.forEach(row => {
      const item = node("div", undefined, "bar-row"); item.setAttribute("role", "listitem");
      const track = node("div", undefined, "track"), fill = node("div", undefined, "fill");
      track.setAttribute("aria-hidden", "true"); fill.style.width = `${Math.max(0, row.value) / maximum * 100}%`;
      track.append(fill); item.append(node("span", row.label, "bar-label"), track, node("span", number(row.value), "bar-value")); chart.append(item);
    }); parent.append(chart);
  }
  function table(parent, headers, rows, caption) {
    const wrap = node("div", undefined, "table-wrap"), t = node("table"), head = node("thead"), tr = node("tr");
    t.append(node("caption", caption));
    headers.forEach(h => {const th = node("th", h); th.scope = "col"; tr.append(th);}); head.append(tr); t.append(head);
    const body = node("tbody"); rows.forEach(values => {const row = node("tr"); values.forEach(v => row.append(node("td", v))); body.append(row);});
    t.append(body); wrap.append(t); parent.append(wrap);
  }
  function renderHistory(data) {
    const container = $("history"); container.replaceChildren(node("p", "PRIMARY VIEW / OWNER-REPORTED HISTORY", "eyebrow"), node("h2", "Historical complaint reports"));
    const metrics = node("div", undefined, "metrics");
    [[number(data.unique_report_count), "Unique reports · primary count"], [`${data.first_report_date || "Unknown"} → ${data.last_report_date || "Unknown"}`, "Report-date coverage · not necessarily continuous"], [number(data.source_row_count), "Source rows · duplicates retained"]].forEach(([value, label], index) => {
      const metric = node("div", undefined, `metric ${index === 0 ? "primary-metric" : index === 1 ? "coverage-metric" : "secondary-metric"}`); metric.append(node("strong", value), node("span", label)); metrics.append(metric);
    }); container.append(metrics, node("p", "One report may have several component rows. Categories can overlap: do not add category counts to get a report total. Complaint counts are not vehicle failure rates.", "notice"));
    const grid = node("div", undefined, "grid"), timeline = node("section"), components = node("section");
    const annual = new Map();
    data.timeline.forEach(bin => {const label = bin.month ? bin.month.slice(0, 4) : "Unknown / conflicting"; annual.set(label, (annual.get(label) || 0) + bin.unique_report_count);});
    bars(timeline, "Report-date timeline · unique reports / year", [...annual].sort(([a], [b]) => a.localeCompare(b)).map(([label, value]) => ({label, value})));
    bars(components, "Structured components · unique reports", data.components.map(c => ({label: componentLabel(c.category), value: c.unique_report_count})));
    grid.append(timeline, components); container.append(grid);
    table(container, ["Component", "Unique reports", "Source rows"], data.components.map(c => [componentLabel(c.category), number(c.unique_report_count), number(c.source_row_count)]), "Structured component accounting (categories can overlap)");
    const unknown = data.timeline.find(b => b.month === null);
    container.append(node("h3", "Data coverage & missing information"), node("p", `Source rows missing report dates: ${number(data.missing_report_date_rows)}. Unknown/conflicting-date bucket: ${number(unknown?.unique_report_count || 0)} reports, ${number(unknown?.source_row_count || 0)} rows. ${data.timeline_policy}`, "muted"), node("p", data.limitation, "notice"));
    metadata(container, "Monthly timeline and source-row counts", data.timeline);
    metadata(container, "Data coverage & provenance", data.provenance);
  }
  function renderRecommendation(parent, data, vehicle) {
    const section = node("section", undefined, "recommendation");
    section.id = "recommendation"; section.setAttribute("aria-labelledby", "recommendation-title");
    const heading = node("h3", "Purchase-readiness guidance"); heading.id = "recommendation-title";
    section.append(heading, node("p", `${vehicle.year} ${vehicle.make} ${vehicle.model}`, "muted"));
    parent.append(section);
    const strings = value => Array.isArray(value) && value.every(item => typeof item === "string");
    const valid = data && typeof data === "object" && typeof data.outcome === "string"
      && Object.hasOwn(outcomeLabels, data.outcome)
      && data.schema_version === "howreliable-purchase-recommendation-1.0"
      && data.policy_version === "howreliable-purchase-readiness-policy-1.0"
      && typeof data.explanation === "string" && data.explanation.trim()
      && strings(data.missing_information) && strings(data.conditions_that_would_change_recommendation)
      && strings(data.limitations) && strings(data.reserved_outcomes)
      && Array.isArray(data.supporting_reasons) && data.supporting_reasons.length
      && data.supporting_reasons.every(reason => reason && typeof reason === "object"
        && typeof reason.explanation === "string" && typeof reason.rule_id === "string"
        && typeof reason.next_step === "string" && strings(reason.evidence_fields)
        && typeof reason.evidence_origin === "string" && Object.hasOwn(originLabels, reason.evidence_origin));
    if (!valid) {
      section.append(node("p", "Recommendation unavailable: the server did not return a supported, complete recommendation. Historical evidence and supplied context remain available. Reassess after checking the local server.", "notice"));
      return "Recommendation unavailable";
    }
    const label = outcomeLabels[data.outcome];
    section.append(node("p", label, "recommendation-outcome"), node("p", data.explanation),
      node("p", "Purchase-readiness guidance, not a reliability score. User-supplied information is not independently verified. Historical NHTSA complaint evidence is separate from this decision, and asking price is not assessed against market values. An independent inspection remains important.", "notice"));
    if (data.outcome === "NOT_RECOMMENDED_UNDER_CURRENT_CONDITIONS") section.append(node("p", "This outcome is reserved and inactive in the current policy. Its appearance is unexpected; verify the server response before relying on it.", "notice"));
    section.append(node("h4", "Supporting reasons"));
    const reasons = node("ul");
    data.supporting_reasons.forEach(reason => {
      const li = node("li", reason.explanation);
      li.append(node("span", ` Evidence origin: ${originLabels[reason.evidence_origin]}.`, "muted"));
      reasons.append(li);
    });
    section.append(reasons, node("h4", "Essential missing information"), node("p", data.missing_information.length ? data.missing_information.map(contextLabel).join(", ") : "No essential fields are missing. Supplied evidence still requires verification."));
    const details = node("details"); details.append(node("summary", "Conditions that could change this recommendation"));
    const conditions = node("ul"); data.conditions_that_would_change_recommendation.forEach(text => conditions.append(node("li", text)));
    details.append(conditions); section.append(details);
    const limits = node("details"); limits.append(node("summary", "Recommendation limitations"));
    const list = node("ul"); data.limitations.forEach(text => list.append(node("li", text))); limits.append(list); section.append(limits);
    metadata(section, "Technical rules and evidence provenance", {schema_version: data.schema_version, policy_version: data.policy_version, reasons: data.supporting_reasons, reserved_outcomes: data.reserved_outcomes});
    return label;
  }
  function renderAssessment(data) {
    const container = $("assessment");
    const heading = node("h2", "Evidence-based purchase assessment");
    heading.id = "assessment-title"; heading.tabIndex = -1;
    container.replaceChildren(node("p", "PRIMARY VIEW / INSPECTION PREPARATION", "eyebrow"), heading,
      node("p", "Historical complaint evidence and inspection prompts. Not an appraisal, reliability score, or buy/avoid verdict.", "notice"));
    const recommendationLabel = renderRecommendation(container, data.recommendation, data.vehicle);
    const context = data.purchase_context;
    table(container, ["Odometer (km)", "Asking price (CAD)", "Maintenance history"], [[context.odometer_km === null ? "Not supplied" : number(context.odometer_km), context.asking_price_cad === null ? "Not supplied" : context.asking_price_cad, context.maintenance_history]], "Supplied purchase context · unverified, not inferred vehicle condition");
    const individual = data.individual_vehicle_context;
    if (individual) {
      const individualDetails = node("details"); individualDetails.append(node("summary", "Individual vehicle details — unverified"));
      table(individualDetails, ["Detail", "Supplied answer"], Object.entries(individual.supplied_information).map(([key, value]) => {
        const control = $(key);
        const label = control?.tagName === "SELECT" ? [...control.options].find(o => o.value === value)?.textContent : value;
        return [contextLabel(key), value === null ? "Not supplied" : label || value];
      }), "User statements only; no documents or actual vehicle condition verified");
      individualDetails.append(node("h3", "Unknown or missing information"), node("p", individual.missing_information.length ? individual.missing_information.map(contextLabel).join(", ") : "No context fields are blank or unknown. This does not verify the supplied information."));
      individualDetails.append(node("h3", "Follow-up questions and next steps"));
      const questions = node("ul");
      individual.follow_up_questions.forEach(text => questions.append(node("li", text)));
      individualDetails.append(questions);
      individual.evidence_limitations.forEach(text => individualDetails.append(node("p", text, "muted")));
      container.append(individualDetails);
    }
    container.append(node("h3", "Reported component concerns"));
    if (data.reported_component_concerns.length) {
      table(container, ["Component", "Unique reports", "Source rows"], data.reported_component_concerns.map(c => [c.label, `${number(c.unique_report_count)} of ${number(c.total_unique_reports)}`, number(c.source_row_count)]), "Backend frequency order, not severity or mechanical risk; categories can overlap");
      data.reported_component_concerns.forEach(c => container.append(node("p", c.interpretation, "muted")));
    } else container.append(node("p", "No specific component concerns can be identified from the available structured labels. This does not establish a problem-free vehicle.", "muted"));
    const coverage = data.component_coverage;
    container.append(node("p", `Unknown/other labels: ${number(coverage.unknown_or_other_unique_reports)} of ${number(coverage.total_unique_reports)} unique reports; ${number(coverage.unknown_or_other_source_rows)} source rows. Specific-component labels: ${number(coverage.specific_component_unique_reports)} unique reports.`, "muted"), node("p", coverage.interpretation, "muted"));
    for (const [basis, title] of [["complaint_supported", "Complaint-supported inspection prompts"], ["generic", "Generic inspection advice"]]) {
      container.append(node("h3", title));
      const list = node("ul");
      data.inspection_priorities.filter(p => p.basis === basis).forEach(p => {
        const li = node("li", p.suggestion);
        if (p.supporting_unique_reports !== null) li.append(node("span", ` Supporting unique reports: ${number(p.supporting_unique_reports)}.`, "muted"));
        list.append(li);
      }); container.append(list);
    }
    container.append(node("h3", "Purchase considerations"));
    data.purchase_considerations.forEach(c => {const p = node("p"); p.append(node("strong", `${c.topic}: `), document.createTextNode(c.explanation)); container.append(p);});
    const evidenceDetails = node("details"); evidenceDetails.append(node("summary", "Evidence limitations"));
    const limitations = node("ul"); data.evidence_limitations.forEach(text => limitations.append(node("li", text))); evidenceDetails.append(limitations); container.append(evidenceDetails);
    metadata(container, "Assessment rules and policy", {schema_version: data.schema_version, methodology_version: data.methodology_version, policy: data.policy});
    return recommendationLabel;
  }
  async function renderPrediction(id, version) {
    const container = $("prediction"); container.replaceChildren(node("h2", experimentTitle), node("p", "Loading the frozen model result…", "muted"));
    try {
      const link = await api(`/api/demo/v1/vehicles/${encodeURIComponent(id)}/prediction`);
      if (version !== resultVersion) return;
      if (link.status !== "supported") {
        container.replaceChildren(node("h2", experimentTitle), node("p", link.status === "ambiguous" ? "Prediction unavailable: the vehicle identity cannot be matched unambiguously." : "No frozen prediction is available for this vehicle. Its historical complaint data remains available.", "notice"), node("p", link.interpretation, "muted")); return;
      }
      // Construct only the documented same-origin route; never follow an arbitrary API URL.
      const data = await api(`/api/v1/cohorts/${encodeURIComponent(id)}`);
      if (version !== resultVersion) return;
      container.replaceChildren(node("p", "SECONDARY VIEW / FROZEN ML EXPERIMENT", "eyebrow"), node("h2", experimentTitle), node("p", "This model estimates whether at least one NHTSA complaint would be reported for the selected vehicle cohort during 2023, using information available through December 2022.", "notice"));
      container.append(node("p", "Not a reliability score. Not the probability that an individual vehicle will fail. Not a current forecast. Not a mechanical failure or repair prediction.", "muted"), node("p", "Predicted probability of 2023 complaint activity", "probability-label"), node("div", `${data.prediction.predicted_future_complaint_percentage.toFixed(1)}%`, "probability"), node("span", data.classification.presentation_label, "badge"), node("p", `Classification: ${data.classification.predicted_classification} · frozen threshold ${data.classification.threshold}`));
      const drivers = [...data.explanation.top_positive_contributors, ...data.explanation.top_negative_contributors];
      table(container, ["Explanation contributor", "Contribution (percentage points)"], drivers.map(d => [d.human_readable_label, (d.contribution_probability * 100).toFixed(2)]), "Top model contributors; associations with model behavior, not causes");
      container.append(node("p", `Historical complaint support: ${number(data.evidence.historical_complaint_support)} · cohort age at cutoff: ${data.evidence.cohort_age_years} years.`, "muted"), node("p", data.general_limitation, "notice"));
      data.limitation_flags.forEach(flag => container.append(node("p", `${flag.title}: ${flag.message}`, "muted")));
      metadata(container, "Historical evidence profile", data.evidence); metadata(container, "Model provenance & explanation method", {provenance: data.provenance, method: data.explanation.method});
    } catch (error) {if (version === resultVersion) container.replaceChildren(node("h2", experimentTitle), node("p", "The frozen ML experiment is unavailable. Your purchase assessment and historical evidence remain available.", "notice"), node("p", error.message, "muted"));}
  }
  make.addEventListener("change", () => discover("model"));
  model.addEventListener("change", () => discover("year"));
  year.addEventListener("change", () => {clearResults(); status(year.value ? "Ready to explore this vehicle." : "Choose a model year.");});
  $("reset").addEventListener("click", async () => {
    $("odometer").value = ""; $("price").value = ""; $("maintenance").value = "unknown";
    contextControls.forEach(control => {control.value = control.tagName === "SELECT" ? control.options[0].value : "";});
    $("inspection_status").setCustomValidity("");
    await discover("make"); if (!make.disabled) make.focus();
  });
  $("retry").addEventListener("click", () => discover("make"));
  for (const id of ["odometer", "price", "maintenance", ...contextControls.map(control => control.id)]) {
    for (const event of ["input", "change"]) $(id).addEventListener(event, () => {
      $("inspection_status").setCustomValidity("");
      clearResults(); status("Purchase context changed. Assess this vehicle again to refresh the results.");
    });
  }
  $("vehicle-form").addEventListener("invalid", () => {
    clearResults(); status("Check the highlighted inputs before requesting an assessment.", true);
  }, true);
  $("vehicle-form").addEventListener("submit", async event => {
    event.preventDefault(); if (!make.value || !model.value || !year.value) return;
    clearResults();
    const version = resultVersion; $("submit").disabled = true; status("Preparing the purchase assessment…");
    try {
      const odometer = $("odometer").value;
      if (odometer !== "" && (!Number.isSafeInteger(Number(odometer)) || Number(odometer) < 0)) throw new Error("Enter an odometer reading as nonnegative whole kilometres within the browser's exact integer range.");
      const payload = {make: make.value, model: model.value, year: Number(year.value), odometer_km: odometer === "" ? null : Number(odometer), asking_price_cad: $("price").value === "" ? null : $("price").value, maintenance_history: $("maintenance").value};
      contextControls.forEach(control => {payload[control.id] = control.tagName === "SELECT" ? control.value : control.value.trim() ? control.value : null;});
      const inspectionConflict = (payload.inspection_status !== "performed" && (payload.inspection_result !== "unavailable" || payload.unresolved_inspection_issues !== "unknown" || payload.inspection_summary !== null)) || (payload.inspection_result === "no_issues_reported" && payload.unresolved_inspection_issues === "yes");
      if (inspectionConflict) {
        $("inspection_status").closest("details").open = true;
        $("inspection_status").setCustomValidity("Inspection findings require Performed. No issues reported cannot have unresolved issues marked Yes.");
        $("inspection_status").reportValidity();
        status("Check the inspection fields: findings require a performed inspection, and no issues reported conflicts with unresolved issues marked Yes.", true);
        return;
      }
      const data = await api("/api/demo/v1/purchase-assessments", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
      if (version !== resultVersion) return;
      const vehicle = data.vehicle;
      if (!vehicle || vehicle.make !== payload.make || vehicle.model !== payload.model || vehicle.year !== payload.year) throw new Error("The returned vehicle does not match your selection. Reassess; no recommendation was displayed.");
      $("vehicle-title").textContent = `${vehicle.year} ${vehicle.make} ${vehicle.model}`;
      const recommendationLabel = renderAssessment(data); renderHistory(data.historical_evidence); $("results").hidden = false;
      $("assessment-title").focus(); status(`Purchase assessment loaded. ${recommendationLabel}. Historical charts, the frozen experiment, and the global NLP sample remain separate views.`);
      // Optional ML must not keep the completed purchase assessment action disabled.
      void renderPrediction(vehicle.id, version);
    } catch (error) {if (version === resultVersion) status(error.message, true);}
    finally {if (version === resultVersion) $("submit").disabled = false;}
  });
  $("load-nlp").addEventListener("click", async () => {
    const container = $("nlp-content"), button = $("load-nlp"); button.disabled = true;
    container.replaceChildren(node("p", "Loading the bounded global sample…", "muted"));
    try {
      const data = await api("/api/demo/v1/nlp/sample-summary");
      container.replaceChildren(node("p", "Global G1 sample only · 1,000 source rows · 691 unique reports. Not filtered by your vehicle selection.", "notice"));
      const grid = node("div", undefined, "grid"), components = node("section"), symptoms = node("section");
      [ [components, "Affirmed components · unique reports", data.summary.components], [symptoms, "Affirmed symptoms · unique reports", data.summary.symptoms] ].forEach(([parent, title, rows]) => {
        bars(parent, title, rows.filter(r => r.assertion === "affirmed").map(r => ({label: r.category, value: r.unique_report_count})));
      }); grid.append(components, symptoms); container.append(grid);
      metadata(container, "Sample denominators and coverage", data.summary.denominators);
      metadata(container, "Older extraction rules & sample provenance", data.provenance);
    } catch (error) {container.replaceChildren(node("p", error.message + " Vehicle history remains available; retry when the sample artifact is restored.", "error"));}
    finally {button.disabled = false;}
  });
  discover("make");
})();
