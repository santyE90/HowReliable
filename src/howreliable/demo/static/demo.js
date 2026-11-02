"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const make = $("make"), model = $("model"), year = $("year");
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
  async function api(path) {
    const response = await fetch(path, {credentials: "omit"});
    if (!response.ok) throw new Error(`Local API request failed (HTTP ${response.status}). Check that the server and required artifacts are available.`);
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
    $("history").replaceChildren(); $("prediction").replaceChildren();
    $("submit").disabled = !year.value;
  }
  async function discover(level) {
    const version = ++selectionVersion;
    clearResults(); $("retry").hidden = true;
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
    } catch (error) {if (version === resultVersion) container.replaceChildren(node("h2", experimentTitle), node("p", error.message, "error"));}
  }
  make.addEventListener("change", () => discover("model"));
  model.addEventListener("change", () => discover("year"));
  year.addEventListener("change", () => {clearResults(); status(year.value ? "Ready to explore this vehicle." : "Choose a model year.");});
  $("reset").addEventListener("click", () => discover("make"));
  $("retry").addEventListener("click", () => discover("make"));
  $("vehicle-form").addEventListener("submit", async event => {
    event.preventDefault(); if (!make.value || !model.value || !year.value) return;
    const version = ++resultVersion; $("submit").disabled = true; status("Loading historical reports…");
    try {
      const q = new URLSearchParams({make: make.value, model: model.value, year: year.value});
      const resolved = await api(`/api/demo/v1/vehicles/resolve?${q}`);
      if (version !== resultVersion) return;
      if (resolved.status !== "matched" || resolved.candidates.length !== 1) throw new Error("No unique vehicle match. Refine or reset your selection; no identity has been guessed.");
      const vehicle = resolved.candidates[0];
      const data = await api(`/api/demo/v1/vehicles/${encodeURIComponent(vehicle.id)}/history`);
      if (version !== resultVersion) return;
      $("vehicle-title").textContent = `${vehicle.year} ${vehicle.make} ${vehicle.model}`;
      renderHistory(data); $("results").hidden = false; status("Historical reports loaded. The forecast and global NLP sample are separate views.");
      await renderPrediction(vehicle.id, version);
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
