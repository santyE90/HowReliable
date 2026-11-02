"use strict";
// Array.from counts Unicode code points, matching Python offsets (not UTF-16 units).
function selectedSpan(text, prefix, selected) {
  const start = Array.from(prefix).length;
  const end = start + Array.from(selected).length;
  if (!selected || Array.from(text).slice(start, end).join("") !== selected) {
    throw new Error("Selection does not match original text.");
  }
  return {start, end, evidence_text: selected};
}
if (typeof module !== "undefined") module.exports = {selectedSpan};

if (typeof document !== "undefined") {
  const el = id => document.getElementById(id);
  let session, work, revision, index = 0, variantIndex = 0, selection = null;
  let editing = null, dirty = false, editorDirty = false;
  const message = text => { el("message").textContent = text; };
  const variant = () => work.annotation.variants[variantIndex];
  const mentions = () => [...variant().component_annotations, ...variant().symptom_annotations];
  const array = kind => variant()[kind + "_annotations"];
  const option = (value, text) => { const o = document.createElement("option"); o.value = value; o.textContent = text; return o; };
  const button = (text, action) => { const b = document.createElement("button"); b.textContent = text; b.onclick = action; return b; };
  async function api(path, payload) {
    const response = await fetch(path, payload === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json", "X-Review-Request": "1"},
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Request failed.");
    return result;
  }
  function changed() {
    dirty = true;
    if (work.state === "pending" || work.state === "annotated" || work.state === "reviewed") {
      work.state = "in_progress"; el("state").value = work.state;
    }
    message("Unsaved changes. Save draft before navigating.");
  }
  function invalidateVariant() {
    const id = variant().variant_id;
    work.completed_variants = work.completed_variants.filter(v => v !== id);
    work.confirmed_empty_variants = work.confirmed_empty_variants.filter(v => v !== id);
    changed();
  }
  function codes() {
    const values = el("kind").value === "component" ? session.components : session.symptoms;
    el("code").replaceChildren(option("", "Choose a label"), ...values.map(v => option(v, v)));
    el("candidates").replaceChildren(...values.map(v => option(v, v)));
  }
  function clearEditor() {
    editorDirty = false;
    editing = null; selection = null;
    el("kind").disabled = false; el("update").disabled = el("cue").disabled = true;
    el("add").disabled = false; el("reason").value = "";
    el("assertion").value = ""; codes();
    el("selection").textContent = "Select evidence in the narrative.";
  }
  function highlight(span) {
    const pre = el("narrative"), text = variant().narrative || "";
    if (!pre.firstChild) return;
    const range = document.createRange();
    range.setStart(pre.firstChild, Array.from(text).slice(0, span.start).join("").length);
    range.setEnd(pre.firstChild, Array.from(text).slice(0, span.end).join("").length);
    const s = window.getSelection(); s.removeAllRanges(); s.addRange(range);
    pre.focus();
  }
  function renderVariant() {
    clearEditor();
    const v = variant();
    el("narrative").textContent = v.narrative === null ? "" : v.narrative;
    el("metadata").textContent = `${v.variant_id}; source rows: ${v.source_row_count}; report dates: ${v.report_dates.join(", ")}; occurrence dates: ${v.occurrence_dates.join(", ")}${v.narrative === null ? "; missing narrative" : ""}`;
    el("complete").checked = work.completed_variants.includes(v.variant_id);
    el("empty").checked = work.confirmed_empty_variants.includes(v.variant_id);
    renderLabels();
  }
  function renderLabels() {
    el("mentions").replaceChildren();
    for (const m of mentions()) {
      const box = document.createElement("div"); box.className = "entry";
      const label = document.createElement("p");
      label.textContent = `${m.kind}: ${m.code} · ${m.assertion} · [${m.start}, ${m.end}) · ${m.evidence_text}`;
      box.append(label, button("Edit / highlight", () => {
        clearEditor(); editing = m.mention_id; el("kind").value = m.kind; codes();
        el("kind").disabled = true; el("code").value = m.code;
        el("assertion").value = m.assertion; el("reason").value = m.ambiguity_reason;
        for (const o of el("candidates").options) o.selected = m.candidate_codes.includes(o.value);
        el("update").disabled = el("cue").disabled = false; el("add").disabled = true;
        highlight(m); message("Editing selected mention; select new evidence only if changing its span.");
      }), button("Remove", () => {
        const links = variant().association_annotations.filter(a => a.component_mention_id === m.mention_id || a.symptom_mention_id === m.mention_id);
        if (links.length && !window.confirm(`Remove mention and its ${links.length} association(s)?`)) return;
        variant()[m.kind + "_annotations"] = array(m.kind).filter(x => x.mention_id !== m.mention_id);
        variant().association_annotations = variant().association_annotations.filter(a => !links.includes(a));
        invalidateVariant(); renderVariant();
      }));
      m.assertion_cue_spans.forEach((cue, n) => {
        const row = document.createElement("p"); row.textContent = `Cue [${cue.start}, ${cue.end}): ${cue.evidence_text}`;
        row.append(button("Remove cue", () => { m.assertion_cue_spans.splice(n, 1); invalidateVariant(); renderVariant(); })); box.append(row);
      });
      el("mentions").append(box);
    }
    for (const kind of ["component", "symptom"]) {
      el(kind + "-endpoint").replaceChildren(option("", "Choose your mention"),
        ...array(kind).map(m => option(m.mention_id, `${m.code} [${m.start}, ${m.end}) ${m.evidence_text}`)));
    }
    el("associations").replaceChildren();
    variant().association_annotations.forEach((a, n) => {
      const box = document.createElement("div"); box.className = "entry";
      const label = document.createElement("p"); label.textContent = `reported_with [${a.start}, ${a.end}): ${a.evidence_text}`;
      box.append(label, button("Highlight", () => highlight(a)), button("Remove association", () => {
        variant().association_annotations.splice(n, 1); invalidateVariant(); renderVariant();
      })); el("associations").append(box);
    });
  }
  function addOrUpdate(update) {
    const old = update ? mentions().find(m => m.mention_id === editing) : null;
    const span = selection || old;
    if (!span || !el("code").value || !el("assertion").value || !el("reason").value.trim()) {
      message("Select evidence and explicitly fill label, assertion and interpretation reason."); return;
    }
    const kind = el("kind").value;
    const id = old ? old.mention_id : `${work.annotation.annotation_id}:${variant().variant_id}:${kind}:${span.start}:${span.end}`;
    if (!old && mentions().some(m => m.mention_id === id)) { message("This span/kind already exists; edit its mention."); return; }
    const value = {mention_id: id, kind, code: el("code").value, assertion: el("assertion").value,
      start: span.start, end: span.end, evidence_text: span.evidence_text, rule_id: "human-guide-1.0",
      ambiguity_reason: el("reason").value.trim(),
      assertion_cue_spans: old ? old.assertion_cue_spans : [],
      candidate_codes: Array.from(el("candidates").selectedOptions).map(o => o.value)};
    if (old) array(kind).splice(array(kind).findIndex(m => m.mention_id === id), 1, value);
    else array(kind).push(value);
    array(kind).sort((a, b) => a.start - b.start || a.end - b.end || a.code.localeCompare(b.code));
    invalidateVariant(); renderVariant();
  }
  async function load(next) {
    if ((dirty || editorDirty) && !window.confirm("Discard unsaved changes? Cancel to save first.")) { el("reports").value = String(index); return; }
    const result = await api(`/api/report/${next}`); index = next; work = result.report; revision = result.revision;
    variantIndex = 0; dirty = false; el("reports").value = String(index);
    el("identity").textContent = `${index + 1} / ${session.reports.length}: ${work.annotation.annotation_id}`;
    el("annotator").value = work.annotation.annotator_id || ""; el("reviewer").value = work.annotation.reviewer_id || "";
    el("notes").value = work.annotation.review_notes || ""; el("state").value = work.state;
    el("variants").replaceChildren(...work.annotation.variants.map((v, n) => option(n, v.variant_id)));
    renderVariant(); message("Loaded. No changes saved automatically.");
  }
  async function refreshSession() {
    session = await api("/api/session");
    el("reports").replaceChildren(...session.reports.map(r => option(r.index, `${r.index + 1}: ${r.state}`)));
    const counts = {}; for (const r of session.reports) counts[r.state] = (counts[r.state] || 0) + 1;
    el("progress").textContent = `${session.taxonomy_version} · Saved progress: ${JSON.stringify(counts)}`;
  }
  function captureSelection() {
    const s = window.getSelection(); if (!s || !s.rangeCount || s.isCollapsed) return;
    const range = s.getRangeAt(0), pre = el("narrative");
    if (!pre.contains(range.startContainer) || !pre.contains(range.endContainer)) return;
    const prefix = range.cloneRange(); prefix.selectNodeContents(pre); prefix.setEnd(range.startContainer, range.startOffset);
    try { selection = selectedSpan(variant().narrative || "", prefix.toString(), range.toString());
      el("selection").textContent = `Selected [${selection.start}, ${selection.end}): ${selection.evidence_text}`;
    } catch (error) { selection = null; message(error.message); }
  }
  el("narrative").addEventListener("mouseup", captureSelection);
  el("narrative").addEventListener("keyup", captureSelection);
  for (const name of ["code", "assertion", "reason", "candidates"]) {
    el(name).addEventListener("input", () => { editorDirty = true; });
  }
  el("kind").onchange = () => { codes(); editorDirty = true; }; el("add").onclick = () => addOrUpdate(false);
  el("update").onclick = () => addOrUpdate(true); el("cancel").onclick = clearEditor;
  el("cue").onclick = () => {
    if (!selection || !editing) { message("Select cue text first."); return; }
    const mention = mentions().find(m => m.mention_id === editing);
    mention.assertion_cue_spans.push({...selection}); invalidateVariant(); renderVariant();
  };
  el("associate").onclick = () => {
    const c = el("component-endpoint").value, s = el("symptom-endpoint").value;
    if (!selection || !c || !s) { message("Choose endpoints and select a supporting clause."); return; }
    variant().association_annotations.push({...selection, component_mention_id: c,
      symptom_mention_id: s, relation: "reported_with", rule_id: "human-guide-1.0"});
    invalidateVariant(); renderVariant();
  };
  for (const name of ["annotator", "reviewer", "notes"]) el(name).oninput = changed;
  el("state").onchange = () => { work.state = el("state").value; dirty = true; message("Status changed; save to validate."); };
  el("complete").onchange = () => {
    const id = variant().variant_id;
    work.completed_variants = work.completed_variants.filter(x => x !== id);
    if (el("complete").checked) work.completed_variants.push(id);
    else { work.confirmed_empty_variants = work.confirmed_empty_variants.filter(x => x !== id); el("empty").checked = false; }
    changed();
  };
  el("empty").onchange = () => {
    if (mentions().length || variant().association_annotations.length) { el("empty").checked = false; message("Remove labels before confirming no mentions."); return; }
    const id = variant().variant_id;
    work.confirmed_empty_variants = work.confirmed_empty_variants.filter(x => x !== id);
    if (el("empty").checked) { work.confirmed_empty_variants.push(id); if (!work.completed_variants.includes(id)) work.completed_variants.push(id); el("complete").checked = true; }
    changed();
  };
  el("variants").onchange = () => {
    if (editorDirty && !window.confirm("Discard unfinished mention editor fields?")) { el("variants").value = String(variantIndex); return; }
    variantIndex = Number(el("variants").value); renderVariant();
  };
  el("reports").onchange = () => load(Number(el("reports").value)).catch(e => message(e.message));
  el("previous").onclick = () => { if (index > 0) load(index - 1).catch(e => message(e.message)); };
  el("next").onclick = () => { if (index + 1 < session.reports.length) load(index + 1).catch(e => message(e.message)); };
  el("save").onclick = async () => {
    if (editorDirty) { message("Add/update the mention, or Clear editor, before saving. Uncommitted editor fields are not annotations."); return; }
    work.annotation.annotator_id = el("annotator").value.trim() || null;
    work.annotation.reviewer_id = el("reviewer").value.trim() || null;
    work.annotation.review_notes = el("notes").value.trim() || null;
    work.state = el("state").value;
    work.annotation.status = {pending: "pending", in_progress: "pending", annotated: "annotated", needs_adjudication: "disputed", reviewed: "reviewed"}[work.state];
    try {
      const saved = await api(`/api/report/${index}`, {revision, report: work}); revision = saved.revision; dirty = false;
      await refreshSession(); el("reports").value = String(index); message(`Saved revision ${revision}. Previous saved version retained in backups.`);
    } catch (error) { message(`Not saved: ${error.message}. Your unsaved edits remain in this tab.`); }
  };
  window.addEventListener("beforeunload", event => { if (dirty || editorDirty) { event.preventDefault(); event.returnValue = ""; } });
  (async () => {
    await refreshSession();
    el("assertion").replaceChildren(option("", "Choose assertion"), ...session.assertions.map(v => option(v, v)));
    el("state").replaceChildren(...session.states.map(v => option(v, v)));
    const next = session.reports.find(r => r.state === "in_progress") || session.reports.find(r => r.state === "pending") || session.reports[0];
    await load(next.index);
  })().catch(error => message(error.message));
}
