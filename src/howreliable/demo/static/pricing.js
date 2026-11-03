"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const form = $("pricing-form"), entries = $("pricing-entries"), output = $("pricing-results");
  let version = 0, nextId = 1;
  const text = (tag, value, cls) => {
    const element = document.createElement(tag);
    if (value !== undefined) element.textContent = String(value);
    if (cls) element.className = cls;
    return element;
  };
  const human = value => String(value).replaceAll("_", " ");
  const enums = {
    transmission: ["unknown", "automatic", "manual", "cvt", "dct", "other"],
    drivetrain: ["unknown", "fwd", "rwd", "awd", "four_wd", "other"],
    province: ["", "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"],
    seller_type: ["unknown", "dealer", "private"],
    condition_status: ["unknown", "no_known_issues_reported", "issues_reported"],
    accident_history: ["unknown", "yes", "no"],
    title_status: ["unknown", "normal_reported", "salvage", "rebuilt", "other"],
    tax_fee_basis: ["unknown", "taxes_and_fees_excluded", "taxes_excluded_fees_included", "taxes_and_fees_included"],
    odometer_unit: ["unknown", "km", "mi"], currency: ["CAD", "USD", "other", "unknown"],
    price_basis: ["cash_asking", "monthly_payment", "valuation", "transaction", "unknown"],
    listing_status: ["unknown", "active_reported", "inactive_reported"],
    permission_basis: ["unknown", "user_owned", "explicit_permission", "licensed", "synthetic"],
    verification_status: ["user_entered_unverified", "user_rechecked"],
    is_subject_vehicle: ["unknown", "yes", "no"]
  };
  const vehicleFields = ["trim", "powertrain", "transmission", "drivetrain", "body_style", "province", "city", "seller_type", "condition_status", "accident_history", "title_status"];
  const referenceFields = ["source_name", "source_listing_id", "listing_url"];
  const labels = {powertrain: "Engine / powertrain", condition_status: "Reported condition", title_status: "Reported title status", observed_on: "Observation date", listed_on: "Original listing date (optional)", asking_price: "Advertised cash asking price", permission_reference: "Permission basis reference (no confidential details)", is_subject_vehicle: "Is this the subject vehicle?", duplicate_of_entry_id: "Confirmed duplicate of entry ID (optional)", possible_duplicate_of_entry_id: "Possible duplicate of entry ID (optional)"};
  const today = () => {const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;};
  function announce(message, error = false) {
    $("pricing-status").textContent = message;
    $("pricing-status").classList.toggle("error", error);
  }
  function invalidate(message = "Pricing inputs changed. Compare again to refresh.") {
    version++; output.replaceChildren(); output.hidden = true;
    $("pricing-submit").disabled = false; announce(message);
  }
  function field(parent, prefix, key) {
    const wrapper = text("div", undefined, "field"), label = text("label", labels[key] || human(key));
    let control;
    if (enums[key]) {
      control = document.createElement("select");
      enums[key].forEach(value => control.append(new Option(value === "" ? "Unknown" : human(value), value)));
    } else {
      control = document.createElement("input"); control.type = "text"; control.maxLength = 100;
      if (key === "permission_attested") {control.type = "checkbox"; label.textContent = "I attest I am permitted to supply these facts (not verified by HowReliable)";}
      else if (["year", "odometer"].includes(key)) {control.type = "number"; control.step = "1"; control.min = key === "year" ? "1886" : "0"; control.max = key === "year" ? "2100" : "9007199254740991";}
      else if (["observed_on", "listed_on"].includes(key)) control.type = "date";
      else if (key === "asking_price") {control.inputMode = "decimal"; control.pattern = "-?[0-9]{1,12}(\\.[0-9]{1,2})?"; control.maxLength = 16;}
      else if (key === "listing_url") control.maxLength = 2048;
      else if (key === "source_listing_id") control.maxLength = 120;
      else if (key === "permission_reference") control.maxLength = 200;
      else if (key.endsWith("entry_id")) {control.maxLength = 40; control.pattern = "[A-Za-z0-9_-]{1,40}";}
    }
    control.id = `${prefix}-${key}`; control.dataset.priceField = key;
    control.setAttribute("aria-describedby", "pricing-help"); label.htmlFor = control.id;
    wrapper.append(label, control); parent.append(wrapper); return control;
  }
  function group(parent, title, prefix, keys, expandable = false) {
    const holder = expandable ? text("details") : text("fieldset");
    holder.append(text(expandable ? "summary" : "legend", title));
    const grid = text("div", undefined, "context-grid"); keys.forEach(key => field(grid, prefix, key));
    holder.append(grid); parent.append(holder);
  }
  group($("pricing-subject-fields"), "Subject configuration and market (unknown values remain unknown)", "price-subject", [...vehicleFields, "tax_fee_basis"]);
  group($("pricing-subject-fields"), "Subject listing reference (optional; never retrieved)", "price-subject", referenceFields, true);
  function addEntry() {
    if (entries.children.length >= 10) return;
    const id = `entry_${nextId++}`, card = text("fieldset", undefined, "comparable"); card.dataset.entryId = id;
    entries.append(card);
    card.append(text("legend", `Comparable ${id}`));
    card.append(text("p", "Make/model/year copied from your selection when added. Check them; other unknown details are not inferred.", "muted"));
    group(card, "Identity and advertised price", id, ["make", "model", "year", "asking_price", "currency", "price_basis", "odometer", "odometer_unit"]);
    for (const key of ["make", "model", "year"]) $(`${id}-${key}`).value = $(key).value;
    group(card, "Source, observation and permission", id, [...referenceFields, "observed_on", "permission_basis", "permission_reference", "permission_attested"]);
    group(card, "Configuration, location and condition (optional)", id, vehicleFields, true);
    group(card, "Other evidence and duplicate references (optional)", id, ["tax_fee_basis", "listed_on", "listing_status", "verification_status", "is_subject_vehicle", "duplicate_of_entry_id", "possible_duplicate_of_entry_id"], true);
    const remove = text("button", `Remove ${id}`, "secondary"); remove.type = "button";
    remove.addEventListener("click", () => {card.remove(); $("pricing-add").disabled = false; invalidate("Comparable removed. Check any duplicate references before comparing again."); $("pricing-add").focus();});
    card.append(remove); $("pricing-add").disabled = entries.children.length >= 10;
    invalidate("Comparable added. Complete known details and permission information.");
    card.querySelector("input").focus();
  }
  function value(prefix, key) {
    const control = $(`${prefix}-${key}`);
    if (control.type === "checkbox") return control.checked;
    if (control.type === "number") return control.value === "" ? null : Number(control.value);
    return control.value.trim() === "" ? null : control.value;
  }
  function snapshot() {
    for (const key of ["make", "model", "year", "odometer", "price"]) {
      if (!$(key).checkValidity()) {$(key).reportValidity(); throw new Error("Choose make, model and year, and correct the shared mileage/price fields above.");}
    }
    const subject = {make: $("make").value, model: $("model").value, year: Number($("year").value), odometer_km: $("odometer").value === "" ? null : Number($("odometer").value), asking_price_cad: $("price").value === "" ? null : $("price").value};
    if (!subject.make || !subject.model || !subject.year) throw new Error("Choose make, model and year above before comparing prices.");
    [...vehicleFields, "tax_fee_basis"].forEach(key => {subject[key] = value("price-subject", key);});
    const ref = Object.fromEntries(referenceFields.map(key => [key, value("price-subject", key)]));
    subject.subject_reference = Object.values(ref).some(v => v !== null) ? ref : null;
    const comparables = [...entries.children].map(card => {
      const id = card.dataset.entryId, vehicle = {};
      ["make", "model", "year", ...vehicleFields].forEach(key => {vehicle[key] = value(id, key);});
      const row = {entry_id: id, vehicle};
      card.querySelectorAll("[data-price-field]").forEach(control => {
        const key = control.dataset.priceField;
        if (!["make", "model", "year", ...vehicleFields].includes(key)) row[key] = value(id, key);
      }); return row;
    });
    return {schema_version: "howreliable-pricing-input-1.0", comparison_date: $("pricing-date").value, subject, comparables};
  }
  const decimal = value => typeof value === "string" && /^-?[0-9]+(?:\.[0-9]+)?$/.test(value);
  // Compare decimal representations without converting money to binary floating point.
  const moneyKey = value => {
    if (value === null) return null;
    if (!decimal(value)) return undefined;
    const negative = value.startsWith("-"), [whole, fraction = ""] = value.replace(/^-/, "").split(".");
    const integer = whole.replace(/^0+(?=\d)/, ""), tail = fraction.replace(/0+$/, "");
    return `${negative && (integer !== "0" || tail) ? "-" : ""}${integer}${tail ? "." + tail : ""}`;
  };
  const cad = value => {if (value === null) return "Unavailable"; const [whole, fraction = ""] = value.split("."); return `CAD ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.padEnd(2, "0")}`;};
  const strings = value => Array.isArray(value) && value.every(v => typeof v === "string");
  function validResult(data, sent) {
    if (!data || data.schema_version !== "howreliable-pricing-comparison-1.0" || data.policy_version !== "howreliable-manual-comparables-policy-1.0" || data.evidence_kind !== "advertised_asking_prices" || data.comparison_date !== sent.comparison_date) return false;
    if (!data.subject || ["make", "model", "year"].some(k => data.subject[k] !== sent.subject[k])) return false;
    if (data.subject.odometer_km !== sent.subject.odometer_km || moneyKey(data.subject.asking_price_cad) !== moneyKey(sent.subject.asking_price_cad)) return false;
    const counts = data.counts, summary = data.price_summary;
    if (!counts || !summary || !["submitted", "primary", "contextual", "excluded", "eligible"].every(k => Number.isInteger(counts[k]) && counts[k] >= 0) || counts.submitted !== sent.comparables.length || counts.submitted !== counts.primary + counts.contextual + counts.excluded || counts.eligible !== counts.primary + counts.contextual || summary.primary_count !== counts.primary) return false;
    const mode = counts.primary === 0 ? "NO_PRIMARY_EVIDENCE" : counts.primary < 3 ? "INDIVIDUAL_ONLY" : "SELECTED_SAMPLE_SUMMARY";
    if (data.display_mode !== mode || !strings(data.limitations) || !data.coverage || !data.method || typeof data.input_sha256 !== "string") return false;
    if (!["minimum_cad", "maximum_cad", "median_cad", "subject_difference_from_median_cad"].every(k => summary[k] === null || decimal(summary[k]))) return false;
    if (counts.primary < 3 && (summary.median_cad !== null || summary.subject_difference_from_median_cad !== null)) return false;
    if (typeof summary.median_display_rounded !== "boolean" || (counts.primary > 0 && (!decimal(summary.minimum_cad) || !decimal(summary.maximum_cad))) || (counts.primary === 0 && (summary.minimum_cad !== null || summary.maximum_cad !== null))) return false;
    if (counts.primary >= 3 && (!decimal(summary.median_cad) || !decimal(summary.median_display_cad))) return false;
    if (!Array.isArray(data.entries) || data.entries.length !== sent.comparables.length) return false;
    if (!data.entries.every((entry, index) => entry?.observation && moneyKey(entry.observation.asking_price) === moneyKey(sent.comparables[index].asking_price) && ["odometer", "odometer_unit", "observed_on", "permission_attested", "currency", "price_basis"].every(key => entry.observation[key] === sent.comparables[index][key]))) return false;
    if (!data.entries.every((entry, index) => entry && entry.observation && entry.observation.entry_id === sent.comparables[index].entry_id && ["PRIMARY_COMPARABLE", "CONTEXTUAL_COMPARABLE", "EXCLUDED"].includes(entry.eligibility) && strings(entry.reason_codes) && strings(entry.warnings) && strings(entry.missing_fields) && strings(entry.mismatched_fields) && [entry.price_difference_cad, entry.odometer_difference_km].every(v => v === null || decimal(v)) && (entry.observation.asking_price === null || decimal(entry.observation.asking_price)))) return false;
    return ["primary", "contextual", "excluded"].every(key => data.entries.filter(entry => entry.eligibility === {primary: "PRIMARY_COMPARABLE", contextual: "CONTEXTUAL_COMPARABLE", excluded: "EXCLUDED"}[key]).length === counts[key]);
  }
  function details(parent, label, data) {const d = text("details"); d.append(text("summary", label), text("pre", JSON.stringify(data, null, 2))); parent.append(d);}
  function render(data) {
    const heading = text("h3", "Selected advertised asking-price comparison"); heading.tabIndex = -1; heading.id = "pricing-result-title";
    output.replaceChildren(heading, text("p", `${data.subject.year} ${data.subject.make} ${data.subject.model} — observed comparison date ${data.comparison_date}`));
    output.append(text("p", `Primary: ${data.counts.primary} · Contextual: ${data.counts.contextual} · Excluded: ${data.counts.excluded} · Submitted: ${data.counts.submitted}`, "notice"));
    if (!data.counts.primary) output.append(text("p", "Comparison unavailable: no primary listings. Review exclusions, unknown details and contextual evidence below."));
    else {
      output.append(text("p", `Primary minimum: ${cad(data.price_summary.minimum_cad)} · Maximum: ${cad(data.price_summary.maximum_cad)}`));
      if (data.counts.primary < 3) output.append(text("p", "Individual comparisons only. A selected-sample median requires at least three primary listings; this is a display rule, not statistical validation."));
      else output.append(text("p", `Selected-sample median: ${cad(data.price_summary.median_display_cad)}${data.price_summary.median_display_rounded ? " (rounded for display)" : ""}`), text("p", `Subject asking price minus selected-sample median: ${cad(data.price_summary.subject_difference_from_median_cad)}. Positive means above this sample, not overpriced.`));
    }
    output.append(text("p", "Advertisements are not verified transaction prices or a market valuation. User-supplied facts are unverified and this selected sample may not represent the market. Mileage, condition and configuration differences are not converted into price adjustments. Price results do not change purchase readiness or cancel inspection concerns.", "notice"));
    for (const entry of data.entries) {
      const row = entry.observation, card = text("section", undefined, "pricing-observation");
      card.append(text("h4", `${row.entry_id}: ${human(entry.eligibility)}`), text("p", `${row.source_name || "Source not supplied"} · ${row.observed_on || "Observation date unknown"} · ${row.currency === "CAD" ? cad(row.asking_price) : `${row.currency}: ${row.asking_price ?? "Price not supplied"}`}`));
      card.append(text("p", `Price difference (comparable minus subject): ${cad(entry.price_difference_cad)} · Mileage difference: ${entry.odometer_difference_km === null ? "Unavailable" : `${entry.odometer_difference_km} km`}`));
      card.append(text("p", entry.reason_codes.map(human).join("; ")));
      entry.warnings.forEach(warning => card.append(text("p", warning, "muted")));
      details(card, "Reason codes, source reference and provenance (references are not fetched)", entry); output.append(card);
    }
    details(output, "Coverage gaps and selected-sample scope", data.coverage);
    const limits = text("details"), list = text("ul"); limits.append(text("summary", "Full pricing limitations")); data.limitations.forEach(v => list.append(text("li", v))); limits.append(list); output.append(limits);
    details(output, "Comparison rules and input provenance", {schema_version: data.schema_version, policy_version: data.policy_version, method: data.method, input_sha256: data.input_sha256});
    output.hidden = false; heading.focus();
  }
  $("pricing-add").addEventListener("click", addEntry);
  function reset() {
    form.reset(); entries.replaceChildren(); nextId = 1; $("pricing-add").disabled = false;
    $("pricing-date").value = today(); invalidate("Pricing entries cleared. Nothing is saved after reload.");
  }
  $("pricing-clear").addEventListener("click", reset); $("reset").addEventListener("click", reset);
  for (const event of ["input", "change"]) {
    form.addEventListener(event, () => invalidate());
    $("vehicle-form").addEventListener(event, e => {
      if (["make", "model", "year"].includes(e.target.id)) $("pricing-subject-fields").querySelectorAll("input,select").forEach(control => {control.value = control.tagName === "SELECT" ? control.options[0].value : "";});
      invalidate("Subject purchase inputs changed. Review subject pricing details and compare again.");
    }, true);
  }
  form.addEventListener("invalid", event => {
    let parent = event.target.parentElement;
    while (parent && parent !== form) {if (parent.tagName === "DETAILS") parent.open = true; parent = parent.parentElement;}
    invalidate(); announce("Correct the highlighted pricing field before submitting.", true);
  }, true);
  form.addEventListener("submit", async event => {
    event.preventDefault(); invalidate(); const token = version;
    try {
      const sent = snapshot(); $("pricing-submit").disabled = true; announce("Comparing manually entered asking prices…");
      const response = await fetch("/api/demo/v1/price-comparisons", {method: "POST", credentials: "omit", cache: "no-store", headers: {"Content-Type": "application/json"}, body: JSON.stringify(sent)});
      if (token !== version) return;
      if (!response.ok) {
        let hint = "Check dates, enum values, references, permissions and duplicate declarations.";
        if (response.status === 422) {
          try {
            const problem = await response.json();
            if (typeof problem.detail === "string") hint = problem.detail.slice(0, 300);
            else if (Array.isArray(problem.detail)) hint = problem.detail.slice(0, 3).map(item => `${Array.isArray(item.loc) ? item.loc.join(" / ").slice(0, 150) : "Input"}: ${typeof item.msg === "string" ? item.msg.slice(0, 200) : "Invalid value"}`).join("; ");
          } catch { /* Keep a bounded generic message for an invalid error response. */ }
        }
        throw new Error(`Price comparison unavailable (HTTP ${response.status}). ${hint} Existing purchase readiness is unchanged.`);
      }
      const data = await response.json(); if (token !== version) return;
      if (!validResult(data, sent)) throw new Error("Price comparison unavailable: incomplete, unsupported or mismatched response. Recheck the local server and compare again.");
      render(data); announce(`Price comparison loaded: ${data.counts.primary} primary, ${data.counts.contextual} contextual, ${data.counts.excluded} excluded. Purchase readiness is unchanged.`);
    } catch (error) {if (token === version) {output.replaceChildren(); output.hidden = true; announce(error instanceof SyntaxError ? "Price comparison unavailable: the server returned invalid JSON. Check the local server and retry." : error.message, true);}}
    finally {if (token === version) $("pricing-submit").disabled = false;}
  });
  $("pricing-date").value = today();
})();
