const warningsCard = document.getElementById("warningsCard");
const warningsBody = document.querySelector("#warningsTable tbody");
const metricsCard = document.getElementById("metricsCard");
const metricsList = document.getElementById("metricsList");
const sharedInputFile = document.getElementById("sharedInputFile");
const sharedConfigFile = document.getElementById("sharedConfigFile");
const camperReviewWrap = document.getElementById("camperReviewWrap");
const camperCabinLayout = document.getElementById("camperCabinLayout");
const camperExportBtn = document.getElementById("camperExportBtn");
const camperBackBtn = document.getElementById("camperBackBtn");
const camperUndoBtn = document.getElementById("camperUndoBtn");
const camperRedoBtn = document.getElementById("camperRedoBtn");
const camperRestartBtn = document.getElementById("camperRestartBtn");
const camperRerunBtn = document.getElementById("camperRerunBtn");
const camperSettingsBtn = document.getElementById("camperSettingsBtn");
const camperUnassignedWrap = document.getElementById("camperUnassignedWrap");
const camperUnassignedList = document.getElementById("camperUnassignedList");
const roommateCounterWrap = document.getElementById("roommateCounterWrap");
const counselorReviewWrap = document.getElementById("counselorReviewWrap");
const counselorBackBtn = document.getElementById("counselorBackBtn");
const counselorDashboardWrap = document.getElementById("counselorDashboardWrap");
const counselorRequestCounterWrap = document.getElementById("counselorRequestCounterWrap");
const counselorCampLayout = document.getElementById("counselorCampLayout");
const counselorUnassignedWrap = document.getElementById("counselorUnassignedWrap");
const counselorUnassignedList = document.getElementById("counselorUnassignedList");
const counselorSingleCampOnly = document.getElementById("counselorSingleCampOnly");
const counselorRedCount = document.getElementById("counselorRedCount");
const counselorGreenCount = document.getElementById("counselorGreenCount");
const counselorBlackCount = document.getElementById("counselorBlackCount");
const counselorPurpleCount = document.getElementById("counselorPurpleCount");
const counselorLoadWrap = document.getElementById("counselorLoadWrap");
const counselorLoadFemaleList = document.getElementById("counselorLoadFemaleList");
const counselorLoadMaleList = document.getElementById("counselorLoadMaleList");

const resultsTab = document.getElementById("resultsTab");
const settingsTab = document.getElementById("settingsTab");
const tabResultsBtn = document.getElementById("tabResultsBtn");
const tabSettingsBtn = document.getElementById("tabSettingsBtn");
const settingsBackBtn = document.getElementById("settingsBackBtn");
const saveSettingsBtn = document.getElementById("saveSettingsBtn");
const resetSettingsBtn = document.getElementById("resetSettingsBtn");
const settingsStatus = document.getElementById("settingsStatus");

let defaultSettings = null;
let currentSettings = null;
let lastCamperMapping = null;
let cabinReviewState = null;
let cabinHistoryPast = [];
let cabinHistoryFuture = [];
let counselorReviewState = null;

function showTab(tabId) {
  const onResults = tabId === "results";
  resultsTab.classList.toggle("hidden", !onResults);
  settingsTab.classList.toggle("hidden", onResults);
}

function setSettingsStatus(msg, isError = false) {
  settingsStatus.textContent = msg || "";
  settingsStatus.className = isError ? "tiny error" : "tiny";
}

function getNum(id, fallback = 0) {
  const v = Number(document.getElementById(id).value);
  return Number.isFinite(v) ? v : fallback;
}

function collectSettingsFromForm() {
  return {
    max_roommate_requests_per_camper: getNum("set_max_roommate_requests", 2),
    cabins: {
      total_per_week: getNum("set_total_per_week", 7),
      max_per_cabin: getNum("set_max_per_cabin", 12),
      min_per_open_cabin: getNum("set_min_per_open_cabin", 7),
      max_disability_per_cabin: getNum("set_max_disability_per_cabin", 2),
      max_same_school_per_cabin: getNum("set_max_same_school_per_cabin", 4),
      strict_grade_span: getNum("set_strict_grade_span", 2),
      strict_adjacent_grades: true,
      allow_grade_relaxation: document.getElementById("set_allow_grade_relaxation").value === "true",
    },
    matching: {
      name_fuzzy_threshold: getNum("set_name_fuzzy_threshold", 82),
      school_fuzzy_threshold: getNum("set_school_fuzzy_threshold", 90),
    },
    counselor_assignment: {
      slots_per_camp: {
        female: getNum("set_counselor_slots_female", 12),
        male: getNum("set_counselor_slots_male", 9),
      },
      friend_bonus: getNum("set_friend_bonus", 8),
      preference_scores: {
        "1": getNum("set_pref1", 100),
        "2": getNum("set_pref2", 70),
        "3": getNum("set_pref3", 40),
      },
    },
  };
}

function fillSettingsForm(settings) {
  document.getElementById("set_total_per_week").value = settings.cabins.total_per_week;
  document.getElementById("set_max_per_cabin").value = settings.cabins.max_per_cabin;
  document.getElementById("set_min_per_open_cabin").value = settings.cabins.min_per_open_cabin;
  document.getElementById("set_max_disability_per_cabin").value = settings.cabins.max_disability_per_cabin;
  document.getElementById("set_max_same_school_per_cabin").value = settings.cabins.max_same_school_per_cabin;
  document.getElementById("set_strict_grade_span").value = settings.cabins.strict_grade_span;
  document.getElementById("set_allow_grade_relaxation").value = settings.cabins.allow_grade_relaxation === false ? "false" : "true";
  document.getElementById("set_max_roommate_requests").value = settings.max_roommate_requests_per_camper;
  document.getElementById("set_name_fuzzy_threshold").value = settings.matching.name_fuzzy_threshold;
  document.getElementById("set_school_fuzzy_threshold").value = settings.matching.school_fuzzy_threshold;
  document.getElementById("set_pref1").value = settings.counselor_assignment.preference_scores["1"] ?? settings.counselor_assignment.preference_scores[1];
  document.getElementById("set_pref2").value = settings.counselor_assignment.preference_scores["2"] ?? settings.counselor_assignment.preference_scores[2];
  document.getElementById("set_pref3").value = settings.counselor_assignment.preference_scores["3"] ?? settings.counselor_assignment.preference_scores[3];
  document.getElementById("set_friend_bonus").value = settings.counselor_assignment.friend_bonus;
  document.getElementById("set_counselor_slots_female").value =
    settings.counselor_assignment.slots_per_camp?.female ?? 12;
  document.getElementById("set_counselor_slots_male").value =
    settings.counselor_assignment.slots_per_camp?.male ?? 9;
}

function clearWarnings() {
  warningsBody.innerHTML = "";
}

function renderWarnings(warnings) {
  clearWarnings();
  warningsCard.classList.remove("hidden");
  if (!warnings || warnings.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = "<td colspan='3'>No warnings.</td>";
    warningsBody.appendChild(row);
    return;
  }
  warnings.forEach((w) => {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${w.level || ""}</td><td>${w.type || ""}</td><td>${w.message || ""}</td>`;
    warningsBody.appendChild(row);
  });
}

function renderMetrics(metrics) {
  metricsCard.classList.remove("hidden");
  metricsList.innerHTML = "";
  (metrics || []).forEach((m) => {
    const item = document.createElement("li");
    item.textContent = `${m.Metric}: ${m.Value}`;
    metricsList.appendChild(item);
  });
}

function setSectionStatus(statusWrapId, statusTextId, message, isError) {
  const wrap = document.getElementById(statusWrapId);
  const text = document.getElementById(statusTextId);
  wrap.classList.remove("hidden");
  text.textContent = message;
  text.className = isError ? "error" : "ok";
}

function createSelect(id, options, selected, allowNone = true) {
  const select = document.createElement("select");
  select.id = id;
  select.name = id;
  if (allowNone) {
    const none = document.createElement("option");
    none.value = "";
    none.textContent = "-- Not mapped --";
    select.appendChild(none);
  }
  options.forEach((opt) => {
    const o = document.createElement("option");
    o.value = opt;
    o.textContent = opt;
    if (opt === selected) {
      o.selected = true;
    }
    select.appendChild(o);
  });
  return select;
}

function addFieldRow(container, label, selectEl) {
  const row = document.createElement("div");
  row.className = "mapping-row";
  const l = document.createElement("label");
  l.textContent = label;
  row.appendChild(l);
  row.appendChild(selectEl);
  container.appendChild(row);
}

function renderCamperMapping(mappingWrap, payload) {
  mappingWrap.innerHTML = "";
  mappingWrap.classList.remove("hidden");
  const suggested = payload.suggested;
  const sheetOptions = payload.sheets || [];

  if (sheetOptions.length > 1) {
    addFieldRow(mappingWrap, "Camper sheet", createSelect("map_camper_sheet", sheetOptions, suggested.sheet, false));
  } else {
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.id = "map_camper_sheet";
    hidden.value = suggested.sheet;
    mappingWrap.appendChild(hidden);
  }

  const cols = payload.columns_by_sheet[suggested.sheet] || [];
  const f = suggested.fields;
  addFieldRow(mappingWrap, "Week (optional)", createSelect("map_week_column", cols, f.week_column));
  addFieldRow(mappingWrap, "First Name (required)", createSelect("map_first_name", cols, f.first_name));
  addFieldRow(mappingWrap, "Last Name (required)", createSelect("map_last_name", cols, f.last_name));
  addFieldRow(mappingWrap, "Gender (required)", createSelect("map_gender", cols, f.gender));
  addFieldRow(mappingWrap, "Grade (required)", createSelect("map_grade", cols, f.grade));
  addFieldRow(mappingWrap, "Date of Birth (optional)", createSelect("map_date_of_birth", cols, f.date_of_birth));
  addFieldRow(mappingWrap, "School (optional)", createSelect("map_school", cols, f.school));
  addFieldRow(mappingWrap, "Disability Flag (optional)", createSelect("map_disability_flag", cols, f.disability_flag));
  addFieldRow(mappingWrap, "Roommate Requests (optional)", createSelect("map_roommate_requests", cols, f.roommate_requests));
}

function renderCounselorMapping(mappingWrap, payload) {
  mappingWrap.innerHTML = "";
  mappingWrap.classList.remove("hidden");
  const suggested = payload.suggested;
  const sheetOptions = payload.sheets || [];
  if (sheetOptions.length > 1) {
    addFieldRow(mappingWrap, "Counselor sheet", createSelect("map_counselor_sheet", sheetOptions, suggested.counselor_sheet, false));
    addFieldRow(mappingWrap, "Camp target sheet", createSelect("map_target_sheet", sheetOptions, suggested.target_sheet, false));
  } else {
    ["counselor_sheet", "target_sheet"].forEach((k) => {
      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.id = `map_${k}`;
      hidden.value = suggested[k];
      mappingWrap.appendChild(hidden);
    });
  }
  const cCols = payload.columns_by_sheet[suggested.counselor_sheet] || [];
  const cf = suggested.counselor_fields;
  addFieldRow(mappingWrap, "First Name (required)", createSelect("map_c_first_name", cCols, cf.first_name));
  addFieldRow(mappingWrap, "Last Name (required)", createSelect("map_c_last_name", cCols, cf.last_name));
  addFieldRow(mappingWrap, "Gender (required)", createSelect("map_c_gender", cCols, cf.gender));
  addFieldRow(mappingWrap, "Email (optional)", createSelect("map_c_email", cCols, cf.email));
  addFieldRow(mappingWrap, "Availability (required)", createSelect("map_c_availability", cCols, cf.availability));
  addFieldRow(mappingWrap, "Preference 1 (optional)", createSelect("map_c_preference_1", cCols, cf.preference_1));
  addFieldRow(mappingWrap, "Preference 2 (optional)", createSelect("map_c_preference_2", cCols, cf.preference_2));
  addFieldRow(mappingWrap, "Preference 3 (optional)", createSelect("map_c_preference_3", cCols, cf.preference_3));
  addFieldRow(mappingWrap, "Willing Camps (optional)", createSelect("map_c_willing_camps", cCols, cf.willing_camps));
  addFieldRow(mappingWrap, "Friend Requests (optional)", createSelect("map_c_friend_requests", cCols, cf.friend_requests));
}

function camperMappingFromUI() {
  return {
    sheet: (document.getElementById("map_camper_sheet") || {}).value || "csv",
    fields: {
      week_column: document.getElementById("map_week_column").value,
      first_name: document.getElementById("map_first_name").value,
      last_name: document.getElementById("map_last_name").value,
      gender: document.getElementById("map_gender").value,
      grade: document.getElementById("map_grade").value,
      date_of_birth: document.getElementById("map_date_of_birth").value,
      school: document.getElementById("map_school").value,
      disability_flag: document.getElementById("map_disability_flag").value,
      roommate_requests: document.getElementById("map_roommate_requests").value,
    },
  };
}

function counselorMappingFromUI() {
  return {
    counselor_sheet: (document.getElementById("map_counselor_sheet") || {}).value || "csv",
    target_sheet: (document.getElementById("map_target_sheet") || {}).value || "csv",
    counselor_fields: {
      first_name: document.getElementById("map_c_first_name").value,
      last_name: document.getElementById("map_c_last_name").value,
      gender: document.getElementById("map_c_gender").value,
      email: document.getElementById("map_c_email").value,
      availability: document.getElementById("map_c_availability").value,
      preference_1: document.getElementById("map_c_preference_1").value,
      preference_2: document.getElementById("map_c_preference_2").value,
      preference_3: document.getElementById("map_c_preference_3").value,
      willing_camps: document.getElementById("map_c_willing_camps").value,
      friend_requests: document.getElementById("map_c_friend_requests").value,
    },
  };
}

function toPositiveInt(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.round(n));
}

function normalizeCounselorGender(value) {
  const text = String(value || "").trim().toLowerCase();
  if (text.startsWith("f") || text.startsWith("g") || text.includes("girl") || text.includes("woman")) return "Female";
  if (text.startsWith("m") || text.startsWith("b") || text.includes("boy") || text.includes("man")) return "Male";
  return "Unknown";
}

function cleanDisplayText(value, fallback = "") {
  const raw = String(value == null ? "" : value).trim();
  if (!raw) return fallback;
  const low = raw.toLowerCase();
  if (["nan", "none", "null", "nat", "undefined"].includes(low)) return fallback;
  if (/^-?\d+\.0+$/.test(raw)) return String(parseInt(raw, 10));
  return raw;
}

function shortCampHeaderLabel(campName) {
  const text = String(campName || "").trim();
  if (!text) return "Camp";
  const m = text.match(/^(sky camp|sky games|western camp)\s*session\s*(\d+)/i);
  if (m) {
    const campType = m[1]
      .split(" ")
      .map((p) => p.charAt(0).toUpperCase())
      .join("");
    return `${campType} S${m[2]}`;
  }
  if (text.length <= 18) return text;
  const initials = text
    .split(/\s+/)
    .filter((p) => p)
    .map((p) => p.charAt(0).toUpperCase())
    .join("");
  return initials || text.slice(0, 18);
}

function normalizeCampSessionName(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const m = raw.match(/\b(sky camp|sky games|western camp)\s+session\s+(\d+)\b/i);
  if (!m) return raw;
  const familyRaw = m[1].toLowerCase();
  const familyMap = {
    "sky camp": "SKY Camp",
    "sky games": "SKY Games",
    "western camp": "Western Camp",
  };
  const family = familyMap[familyRaw] || m[1];
  return `${family} Session ${m[2]}`;
}

function isLikelyCampSessionName(value) {
  const text = normalizeCampSessionName(value).toLowerCase();
  if (!text) return false;
  return /^(sky camp|sky games|western camp)\s+session\s+\d+$/.test(text);
}

function buildCounselorReviewState(payload) {
  const state = {
    campsByKey: {},
    campOrder: [],
    assignmentById: {},
    assignmentCampById: {},
    unassigned: [],
    warningSummaryByCamp: {},
    eligibilityByCamp: {},
    loadStatusByCounselorId: {},
    loadMetaByCounselorId: {},
  };
  const loadSummary = Array.isArray(payload?.counselor_load_summary) ? payload.counselor_load_summary : [];
  loadSummary.forEach((row) => {
    const cid = String(row?.counselor_id || "").trim();
    if (!cid) return;
    state.loadMetaByCounselorId[cid] = {
      counselor_id: cid,
      counselor_name: String(row?.counselor_name || "").trim(),
      gender: String(row?.gender || "").trim(),
      willing_raw: String(row?.willing_raw || "").trim(),
      willing_capacity: toPositiveInt(row?.willing_capacity),
    };
    state.loadStatusByCounselorId[cid] = {
      emoji: String(row?.status_emoji || "").trim(),
      reason: String(row?.status_reason || "").trim(),
    };
  });
  const fixedOrderRaw = Array.isArray(payload?.fixed_camp_order) ? payload.fixed_camp_order : [];
  const fixedOrder = fixedOrderRaw
    .map((x) => normalizeCampSessionName(cleanDisplayText(x)))
    .filter((x) => isLikelyCampSessionName(x));
  const catalog = fixedOrder.length > 0
    ? fixedOrder
    : (Array.isArray(payload?.camp_catalog) ? payload.camp_catalog : [])
        .map((x) => normalizeCampSessionName(cleanDisplayText(x)))
        .filter((x) => isLikelyCampSessionName(x));
  catalog.forEach((name) => {
    const camp = cleanDisplayText(name);
    if (!camp) return;
    if (state.campsByKey[camp]) return;
    state.campsByKey[camp] = {
      camp,
      targetTotal: 0,
      targetFemale: 0,
      targetMale: 0,
      members: [],
    };
    state.campOrder.push(camp);
  });
  const allowedCampSet = new Set(state.campOrder.map((x) => String(x)));
  const targetSummary = Array.isArray(payload?.target_summary) ? payload.target_summary : [];
  targetSummary.forEach((row) => {
    const camp = normalizeCampSessionName(cleanDisplayText(row.Camp));
    if (!camp) return;
    if (!isLikelyCampSessionName(camp)) return;
    if (allowedCampSet.size > 0 && !allowedCampSet.has(camp)) return;
    if (!state.campsByKey[camp]) {
      state.campsByKey[camp] = { camp, targetTotal: 0, targetFemale: 0, targetMale: 0, members: [] };
      state.campOrder.push(camp);
      allowedCampSet.add(camp);
    }
    state.campsByKey[camp].targetTotal = toPositiveInt(row["Target Total"]);
    state.campsByKey[camp].targetFemale = toPositiveInt(row["Target Female"]);
    state.campsByKey[camp].targetMale = toPositiveInt(row["Target Male"]);
  });

  (payload?.warning_summary || []).forEach((w) => {
    const camp = String(w.camp || "").trim();
    if (!camp) return;
    state.warningSummaryByCamp[camp] = {
      unfilledTotal: toPositiveInt(w.unfilled_total),
      unfilledFemale: toPositiveInt(w.unfilled_female),
      unfilledMale: toPositiveInt(w.unfilled_male),
    };
  });

  (payload?.eligibility_summary || []).forEach((row) => {
    const camp = normalizeCampSessionName(cleanDisplayText(row.camp));
    if (!camp || !isLikelyCampSessionName(camp)) return;
    state.eligibilityByCamp[camp] = {
      total: toPositiveInt(row.eligible_total),
      female: toPositiveInt(row.eligible_female),
      male: toPositiveInt(row.eligible_male),
    };
  });

  (payload?.assignments || []).forEach((row, idx) => {
    const camp = normalizeCampSessionName(cleanDisplayText(row.Camp));
    if (!camp) return;
    if (!isLikelyCampSessionName(camp)) return;
    if (allowedCampSet.size > 0 && !allowedCampSet.has(camp)) return;
    const counselorId = String(row["Counselor ID"] || `assigned-${idx}`);
    const assignmentId = `assigned::${counselorId}::${idx}`;
    const counselor = {
      assignmentId,
      counselorId,
      name: cleanDisplayText(row["Counselor Name"], "Unknown"),
      gender: cleanDisplayText(row.Gender, ""),
      email: cleanDisplayText(row.Email, ""),
      slotNeed: cleanDisplayText(row["Slot Gender Need"], "Any"),
      prefMatch: String(row["Preference Match"] || "none"),
      availability: "",
      friendIds: Array.isArray(row["Friend IDs"]) ? row["Friend IDs"].map(String) : [],
      friendUnmatched: Array.isArray(row["Friend Unmatched Names"]) ? row["Friend Unmatched Names"].map(String) : [],
      requestedByIds: Array.isArray(row["Requested By IDs"]) ? row["Requested By IDs"].map(String) : [],
      friendStatusDetail: [],
      requestedByOthers: false,
      loadStatusEmoji: state.loadStatusByCounselorId[counselorId]?.emoji || "",
      loadStatusReason: state.loadStatusByCounselorId[counselorId]?.reason || "",
    };
    if (!state.campsByKey[camp]) {
      state.campsByKey[camp] = {
        camp,
        targetTotal: 0,
        targetFemale: 0,
        targetMale: 0,
        members: [],
      };
      state.campOrder.push(camp);
      allowedCampSet.add(camp);
    }
    state.campsByKey[camp].members.push(counselor);
    state.assignmentById[assignmentId] = counselor;
    state.assignmentCampById[assignmentId] = camp;
  });

  (payload?.unassigned_counselors || []).forEach((row, idx) => {
    const counselorId = String(row["Counselor ID"] || `unassigned-${idx}`);
    const assignmentId = `unassigned::${counselorId}::${idx}`;
    const counselor = {
      assignmentId,
      counselorId,
      name: cleanDisplayText(row["Counselor Name"], "Unknown"),
      gender: cleanDisplayText(row.Gender, ""),
      email: cleanDisplayText(row.Email, ""),
      slotNeed: "Any",
      prefMatch: "none",
      availability: cleanDisplayText(row.Availability, ""),
      reason: cleanDisplayText(row.Reason, ""),
      friendIds: [],
      friendUnmatched: [],
      requestedByIds: [],
      friendStatusDetail: [],
      requestedByOthers: false,
      loadStatusEmoji: state.loadStatusByCounselorId[counselorId]?.emoji || "",
      loadStatusReason: state.loadStatusByCounselorId[counselorId]?.reason || "",
    };
    state.unassigned.push(counselor);
    state.assignmentById[assignmentId] = counselor;
    state.assignmentCampById[assignmentId] = "__UNASSIGNED__";
  });

  state.campOrder.sort((a, b) => a.localeCompare(b));
  if (fixedOrder.length > 0) {
    const fixedIndex = new Map(fixedOrder.map((name, idx) => [String(name), idx]));
    state.campOrder.sort((a, b) => {
      const ai = fixedIndex.has(a) ? fixedIndex.get(a) : Number.MAX_SAFE_INTEGER;
      const bi = fixedIndex.has(b) ? fixedIndex.get(b) : Number.MAX_SAFE_INTEGER;
      if (ai !== bi) return ai - bi;
      return a.localeCompare(b);
    });
  }
  return state;
}

function counselorSummaryTotals(state) {
  const camps = state.campOrder.map((camp) => state.campsByKey[camp]);
  const targetTotal = camps.reduce((acc, c) => acc + toPositiveInt(c.targetTotal), 0);
  const assignedTotal = camps.reduce((acc, c) => acc + c.members.length, 0);
  const unassigned = (state.unassigned || []).length;
  const unfilledTotal = camps.reduce((acc, c) => acc + Math.max(0, toPositiveInt(c.targetTotal) - c.members.length), 0);
  const overfilledTotal = camps.reduce((acc, c) => acc + Math.max(0, c.members.length - toPositiveInt(c.targetTotal)), 0);
  return {
    targetTotal,
    assignedTotal,
    unassigned,
    unfilledTotal,
    overfilledTotal,
  };
}

function recomputeCounselorFriendStatus(state) {
  if (!state) return;
  const campCounselorSets = {};
  state.campOrder.forEach((camp) => {
    const members = state.campsByKey[camp]?.members || [];
    campCounselorSets[camp] = new Set(members.map((m) => String(m.counselorId || "")));
  });
  const requestedByIds = new Set();
  Object.values(state.assignmentById || {}).forEach((entry) => {
    (entry.friendIds || []).forEach((fid) => {
      if (fid) requestedByIds.add(String(fid));
    });
  });
  Object.values(state.assignmentById || {}).forEach((entry) => {
    const camp = state.assignmentCampById[entry.assignmentId];
    const campSet = camp && campCounselorSets[camp] ? campCounselorSets[camp] : new Set();
    const detail = [];
    (entry.friendIds || []).forEach((fid) => {
      if (campSet.has(String(fid))) {
        detail.push({ emoji: "🟢", target: fid, status: "friend request fulfilled in this camp" });
      } else {
        detail.push({ emoji: "🔴", target: fid, status: "friend requested counselor is not in this camp" });
      }
    });
    (entry.friendUnmatched || []).forEach((name) => {
      detail.push({ emoji: "⚫️", target: name, status: "requested friend not found in counselor list" });
    });
    entry.friendStatusDetail = detail;
    entry.requestedByOthers = requestedByIds.has(String(entry.counselorId || ""));
  });
}

function updateCounselorRequestCounters(state) {
  if (!counselorRequestCounterWrap) return;
  if (!state || !state.assignmentById) {
    counselorRequestCounterWrap.textContent = "";
    if (counselorRedCount) counselorRedCount.textContent = "🔴 0";
    if (counselorGreenCount) counselorGreenCount.textContent = "🟢 0";
    if (counselorBlackCount) counselorBlackCount.textContent = "⚫️ 0";
    if (counselorPurpleCount) counselorPurpleCount.textContent = "🟪 0";
    return;
  }
  let green = 0;
  let red = 0;
  let black = 0;
  let purple = 0;
  Object.values(state.assignmentById).forEach((entry) => {
    (entry.friendStatusDetail || []).forEach((d) => {
      if (d.emoji === "🟢") green += 1;
      if (d.emoji === "🔴") red += 1;
      if (d.emoji === "⚫️") black += 1;
    });
    if (entry.requestedByOthers) purple += 1;
  });
  counselorRequestCounterWrap.textContent = `Friend request totals: 🔴 ${red} | 🟢 ${green} | ⚫️ ${black} | 🟪 ${purple}`;
  if (counselorRedCount) counselorRedCount.textContent = `🔴 ${red}`;
  if (counselorGreenCount) counselorGreenCount.textContent = `🟢 ${green}`;
  if (counselorBlackCount) counselorBlackCount.textContent = `⚫️ ${black}`;
  if (counselorPurpleCount) counselorPurpleCount.textContent = `🟪 ${purple}`;
}

function buildCounselorLoadRowsFromState(state) {
  if (!state) return [];
  const assignedCountByCounselorId = {};
  Object.values(state.assignmentById || {}).forEach((entry) => {
    const counselorId = String(entry?.counselorId || "").trim();
    if (!counselorId) return;
    const campKey = state.assignmentCampById?.[entry.assignmentId];
    if (campKey === "__UNASSIGNED__") return;
    assignedCountByCounselorId[counselorId] = (assignedCountByCounselorId[counselorId] || 0) + 1;
  });
  const allCounselorIds = new Set();
  Object.keys(state.loadMetaByCounselorId || {}).forEach((cid) => allCounselorIds.add(String(cid)));
  Object.values(state.assignmentById || {}).forEach((entry) => {
    const counselorId = String(entry?.counselorId || "").trim();
    if (counselorId) allCounselorIds.add(counselorId);
  });
  const rows = [];
  allCounselorIds.forEach((cid) => {
    const meta = state.loadMetaByCounselorId?.[cid] || {};
    const assignedCount = toPositiveInt(assignedCountByCounselorId[cid] || 0);
    const willingRaw = String(meta.willing_raw || "").trim();
    const willingNorm = willingRaw.toLowerCase();
    const willingCapacity = toPositiveInt(meta.willing_capacity || 0);
    let status_emoji = "👌🏼";
    let status_reason = "No willing-camps value provided.";
    if (willingNorm) {
      const isUnlimited = willingNorm.includes("as many")
        || ["all", "any", "unlimited", "no limit"].includes(willingNorm);
      if (isUnlimited) {
        status_emoji = assignedCount === 0 ? "🥶" : "👌🏼";
        status_reason = assignedCount === 0
          ? "Unlimited willingness but currently assigned to zero camps."
          : "Unlimited willingness value.";
      } else if (assignedCount > willingCapacity) {
        status_emoji = "🥵";
        status_reason = "Assigned to more camps than willing-camps value.";
      } else if (assignedCount === willingCapacity) {
        status_emoji = "👌🏼";
        status_reason = "Assigned to exactly willing-camps value.";
      } else {
        status_emoji = "🥶";
        status_reason = "Assigned to fewer camps than willing-camps value.";
      }
    }
    state.loadStatusByCounselorId[cid] = { emoji: status_emoji, reason: status_reason };
    rows.push({
      counselor_id: cid,
      counselor_name: String(meta.counselor_name || "").trim() || cid,
      gender: String(meta.gender || "").trim(),
      assigned_count: assignedCount,
      willing_raw: willingRaw,
      willing_capacity: willingCapacity,
      status_emoji,
      status_reason,
    });
  });
  rows.sort((a, b) => String(a.counselor_name || "").localeCompare(String(b.counselor_name || "")));
  Object.values(state.assignmentById || {}).forEach((entry) => {
    const cid = String(entry?.counselorId || "").trim();
    const status = state.loadStatusByCounselorId?.[cid] || {};
    entry.loadStatusEmoji = String(status.emoji || "");
    entry.loadStatusReason = String(status.reason || "");
  });
  return rows;
}

function renderCounselorLoadStatus(rows) {
  if (!counselorLoadWrap || !counselorLoadFemaleList || !counselorLoadMaleList) return;
  counselorLoadFemaleList.innerHTML = "";
  counselorLoadMaleList.innerHTML = "";
  const list = Array.isArray(rows) ? rows : [];
  if (list.length === 0) {
    counselorLoadWrap.classList.add("hidden");
    return;
  }
  counselorLoadWrap.classList.remove("hidden");
  const femaleRows = [];
  const maleRows = [];
  list.forEach((row) => {
    const gender = normalizeCounselorGender(row?.gender || "");
    if (gender === "Female") femaleRows.push(row);
    else maleRows.push(row);
  });
  const appendRows = (targetList, rowsToRender) => {
    rowsToRender.forEach((row) => {
      const li = document.createElement("li");
      const emoji = String(row.status_emoji || "");
      const name = String(row.counselor_name || "Unknown");
      const assigned = toPositiveInt(row.assigned_count);
      const willingRaw = String(row.willing_raw || "").trim() || "not provided";
      li.textContent = `${emoji} ${name} - assigned ${assigned}, willing camps: ${willingRaw}`;
      li.title = String(row.status_reason || "");
      targetList.appendChild(li);
    });
  };
  appendRows(counselorLoadFemaleList, femaleRows);
  appendRows(counselorLoadMaleList, maleRows);
  if (femaleRows.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No girls found.";
    counselorLoadFemaleList.appendChild(li);
  }
  if (maleRows.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No guys found.";
    counselorLoadMaleList.appendChild(li);
  }
}

function renderCounselorDashboard(state) {
  if (!counselorDashboardWrap) return;
  if (!state) {
    counselorDashboardWrap.textContent = "";
    return;
  }
  const totals = counselorSummaryTotals(state);
  const campLines = state.campOrder.map((camp) => {
    const c = state.campsByKey[camp];
    const assigned = c.members.length;
    const target = toPositiveInt(c.targetTotal);
    const warning = state.warningSummaryByCamp[camp];
    const eligibility = state.eligibilityByCamp[camp];
    const warnText = warning
      ? ` | algorithm unfilled: ${warning.unfilledTotal} (F ${warning.unfilledFemale} / M ${warning.unfilledMale})`
      : "";
    const eligText = eligibility
      ? ` | eligible ${eligibility.total} (F ${eligibility.female} / M ${eligibility.male})`
      : "";
    return `${camp}: assigned ${assigned} / target ${target}${warnText}${eligText}`;
  });
  counselorDashboardWrap.innerHTML = "";
  const top = document.createElement("p");
  top.className = "tiny";
  top.textContent =
    `Counselor totals: assigned ${totals.assignedTotal} / target ${totals.targetTotal} | ` +
    `unfilled ${totals.unfilledTotal} | overfilled ${totals.overfilledTotal} | currently unassigned ${totals.unassigned}`;
  counselorDashboardWrap.appendChild(top);
  const ul = document.createElement("ul");
  ul.className = "tiny";
  campLines.forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    ul.appendChild(li);
  });
  counselorDashboardWrap.appendChild(ul);
}

function renderCounselorCardMember(list, counselor, state) {
  const li = document.createElement("li");
  li.className = "camper-row";
  li.draggable = true;
  li.dataset.assignmentId = counselor.assignmentId;
  li.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/counselor-assignment-id", counselor.assignmentId);
    e.dataTransfer.effectAllowed = "move";
  });
  const nameSpan = document.createElement("span");
  nameSpan.className = "camper-name";
  const parts = [counselor.name || "Unknown"];
  if (counselor.loadStatusEmoji) parts.push(counselor.loadStatusEmoji);
  if (counselor.gender) parts.push(`(${counselor.gender})`);
  if (counselor.slotNeed && counselor.slotNeed !== "Any") parts.push(`[slot: ${counselor.slotNeed}]`);
  nameSpan.textContent = parts.join(" ");
  (counselor.friendStatusDetail || []).forEach((d) => {
    const em = document.createElement("span");
    em.className = "roommate-emoji";
    em.textContent = ` ${d.emoji}`;
    em.title = `${d.target || "friend"} - ${d.status || "friend request status"}`;
    nameSpan.appendChild(em);
  });
  if (counselor.requestedByOthers) {
    const em = document.createElement("span");
    em.className = "roommate-emoji requested-by-emoji";
    em.textContent = " 🟪";
    em.title = "This counselor was requested by someone else";
    nameSpan.appendChild(em);
  }
  li.appendChild(nameSpan);
  if (counselor.email) {
    const meta = document.createElement("span");
    meta.className = "camper-grade";
    meta.textContent = counselor.email;
    li.appendChild(meta);
  }
  if (counselor.reason) {
    const reason = document.createElement("span");
    reason.className = "tiny";
    reason.textContent = ` - ${counselor.reason}`;
    li.appendChild(reason);
  }
  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "counselor-delete-btn";
  deleteBtn.textContent = "×";
  deleteBtn.title = "Delete this counselor from this week only";
  deleteBtn.draggable = false;
  deleteBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const changed = deleteCounselorAssignment(state, counselor.assignmentId);
    if (changed) {
      renderCounselorLayout(state);
      renderCounselorDashboard(state);
      setSectionStatus("counselorStatusWrap", "counselorStatusText", "Deleted counselor for this week only.", false);
    }
  });
  li.appendChild(deleteBtn);
  list.appendChild(li);
}

function canDropCounselorToSection(counselor, targetSection) {
  if (!targetSection || targetSection === "Any") return true;
  const gender = normalizeCounselorGender(counselor.gender);
  if (targetSection === "Female") return gender === "Female";
  if (targetSection === "Male") return gender === "Male";
  return true;
}

function moveCounselorBetweenCamps(state, assignmentId, targetCampKey) {
  if (!state || !assignmentId || !targetCampKey) return false;
  const sourceKey = state.assignmentCampById[assignmentId];
  if (!sourceKey || sourceKey === targetCampKey) return false;
  const counselor = state.assignmentById[assignmentId];
  if (!counselor) return false;

  if (sourceKey === "__UNASSIGNED__") {
    const idx = state.unassigned.findIndex((x) => x.assignmentId === assignmentId);
    if (idx >= 0) state.unassigned.splice(idx, 1);
  } else if (state.campsByKey[sourceKey]) {
    const members = state.campsByKey[sourceKey].members;
    const idx = members.findIndex((x) => x.assignmentId === assignmentId);
    if (idx >= 0) members.splice(idx, 1);
  }

  if (targetCampKey === "__UNASSIGNED__") {
    state.unassigned.push(counselor);
  } else {
    if (!state.campsByKey[targetCampKey]) return false;
    state.campsByKey[targetCampKey].members.push(counselor);
  }
  state.assignmentCampById[assignmentId] = targetCampKey;
  recomputeCounselorFriendStatus(state);
  updateCounselorRequestCounters(state);
  renderCounselorLoadStatus(buildCounselorLoadRowsFromState(state));
  return true;
}

function deleteCounselorAssignment(state, assignmentId) {
  if (!state || !assignmentId) return false;
  const sourceKey = state.assignmentCampById[assignmentId];
  if (!sourceKey) return false;
  if (sourceKey === "__UNASSIGNED__") {
    const idx = state.unassigned.findIndex((x) => x.assignmentId === assignmentId);
    if (idx >= 0) state.unassigned.splice(idx, 1);
  } else if (state.campsByKey[sourceKey]) {
    const members = state.campsByKey[sourceKey].members;
    const idx = members.findIndex((x) => x.assignmentId === assignmentId);
    if (idx >= 0) members.splice(idx, 1);
  }
  delete state.assignmentCampById[assignmentId];
  delete state.assignmentById[assignmentId];
  recomputeCounselorFriendStatus(state);
  updateCounselorRequestCounters(state);
  renderCounselorLoadStatus(buildCounselorLoadRowsFromState(state));
  return true;
}

function splitCampMembersBySection(members) {
  const female = [];
  const male = [];
  (members || []).forEach((c) => {
    const g = normalizeCounselorGender(c.gender);
    if (g === "Female") {
      female.push(c);
      return;
    }
    if (g === "Male") {
      male.push(c);
      return;
    }
    if (String(c.slotNeed || "").toLowerCase() === "male") male.push(c);
    else female.push(c);
  });
  female.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  male.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  return { female, male };
}

function statusLabel(assigned, slots) {
  const left = Math.max(0, slots - assigned);
  if (left === 0) return "FULL";
  if (left === 1) return "1 LEFT";
  return `${left} LEFT`;
}

function buildCounselorChip(counselor, state) {
  const chip = document.createElement("span");
  chip.className = "counselor-chip";
  chip.draggable = true;
  chip.dataset.assignmentId = counselor.assignmentId;
  const pref = String(counselor.prefMatch || "none");
  const prefLabel = pref === "1" || pref === "2" || pref === "3" ? ` P${pref}` : "";
  const loadEmoji = counselor.loadStatusEmoji ? ` ${counselor.loadStatusEmoji}` : "";
  chip.textContent = `${counselor.name || "Unknown"}${loadEmoji}${prefLabel}`;
  (counselor.friendStatusDetail || []).forEach((d) => {
    const em = document.createElement("span");
    em.className = "roommate-emoji";
    em.textContent = ` ${d.emoji}`;
    em.title = `${d.target || "friend"} - ${d.status || "friend request status"}`;
    chip.appendChild(em);
  });
  if (counselor.requestedByOthers) {
    const em = document.createElement("span");
    em.className = "roommate-emoji requested-by-emoji";
    em.textContent = " 🟪";
    em.title = "This counselor was requested by someone else";
    chip.appendChild(em);
  }
  chip.title = counselor.loadStatusReason || counselor.email || counselor.availability || "";
  chip.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/counselor-assignment-id", counselor.assignmentId);
    e.dataTransfer.effectAllowed = "move";
  });
  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "counselor-delete-btn";
  deleteBtn.textContent = "×";
  deleteBtn.title = "Delete this counselor from this week only";
  deleteBtn.draggable = false;
  deleteBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const changed = deleteCounselorAssignment(state, counselor.assignmentId);
    if (changed) {
      renderCounselorLayout(state);
      renderCounselorDashboard(state);
      setSectionStatus("counselorStatusWrap", "counselorStatusText", "Deleted counselor for this week only.", false);
    }
  });
  chip.appendChild(deleteBtn);
  return chip;
}

function renderCounselorUnassigned(state) {
  if (!counselorUnassignedWrap || !counselorUnassignedList) return;
  counselorUnassignedList.innerHTML = "";
  const members = [...(state?.unassigned || [])].sort((a, b) =>
    String(a.name || "").localeCompare(String(b.name || ""))
  );
  if (members.length === 0) {
    counselorUnassignedWrap.classList.add("hidden");
    return;
  }
  counselorUnassignedWrap.classList.remove("hidden");
  counselorUnassignedList.ondragover = (e) => {
    e.preventDefault();
    counselorUnassignedList.classList.add("drop-hover");
  };
  counselorUnassignedList.ondragleave = () => {
    counselorUnassignedList.classList.remove("drop-hover");
  };
  counselorUnassignedList.ondrop = (e) => {
    e.preventDefault();
    counselorUnassignedList.classList.remove("drop-hover");
    const assignmentId = e.dataTransfer.getData("text/counselor-assignment-id");
    if (!assignmentId) return;
    const changed = moveCounselorBetweenCamps(state, assignmentId, "__UNASSIGNED__");
    if (changed) {
      renderCounselorLayout(state);
      renderCounselorDashboard(state);
      setSectionStatus("counselorStatusWrap", "counselorStatusText", "Manual counselor move applied in review view.", false);
    }
  };
  members.forEach((c) => renderCounselorCardMember(counselorUnassignedList, c, state));
}

function renderCounselorLayout(state) {
  if (!counselorCampLayout) return;
  counselorCampLayout.innerHTML = "";
  if (!state || state.campOrder.length === 0) {
    counselorCampLayout.textContent = "No counselor camp rows were generated.";
    renderCounselorUnassigned(state);
    return;
  }
  const tableWrap = document.createElement("div");
  tableWrap.className = "table-wrap";
  const table = document.createElement("table");
  table.className = "counselor-matrix";
  const header = document.createElement("thead");
  const hr = document.createElement("tr");
  const first = document.createElement("th");
  first.textContent = "Slot";
  hr.appendChild(first);
  state.campOrder.forEach((campKey) => {
    const th = document.createElement("th");
    th.title = campKey;
    const shortLabel = shortCampHeaderLabel(campKey);
    if (shortLabel === campKey) {
      th.innerHTML = `<div class="camp-col-head-short">${shortLabel}</div>`;
    } else {
      th.innerHTML = `<div class="camp-col-head-short">${shortLabel}</div><div class="camp-col-head-full">${campKey}</div>`;
    }
    hr.appendChild(th);
  });
  header.appendChild(hr);
  table.appendChild(header);

  const body = document.createElement("tbody");
  const campSplit = {};
  state.campOrder.forEach((campKey) => {
    campSplit[campKey] = splitCampMembersBySection(state.campsByKey[campKey].members || []);
  });
  const femaleSlotsByCamp = {};
  const maleSlotsByCamp = {};
  state.campOrder.forEach((campKey) => {
    femaleSlotsByCamp[campKey] = Math.max(0, toPositiveInt(state.campsByKey[campKey].targetFemale));
    maleSlotsByCamp[campKey] = Math.max(0, toPositiveInt(state.campsByKey[campKey].targetMale));
  });
  const maxFemaleSlots = Math.max(0, ...Object.values(femaleSlotsByCamp));
  const maxMaleSlots = Math.max(0, ...Object.values(maleSlotsByCamp));

  const femaleStatusRow = document.createElement("tr");
  femaleStatusRow.className = "slot-status-row";
  const femaleStatusLabel = document.createElement("td");
  femaleStatusLabel.textContent = "Female Status";
  femaleStatusRow.appendChild(femaleStatusLabel);
  state.campOrder.forEach((campKey) => {
    const td = document.createElement("td");
    td.textContent = statusLabel(campSplit[campKey].female.length, femaleSlotsByCamp[campKey]);
    femaleStatusRow.appendChild(td);
  });
  body.appendChild(femaleStatusRow);

  for (let i = 0; i < maxFemaleSlots; i += 1) {
    const row = document.createElement("tr");
    row.className = "slot-row";
    const label = document.createElement("td");
    label.textContent = `Female ${i + 1}`;
    row.appendChild(label);
    state.campOrder.forEach((campKey) => {
      const td = document.createElement("td");
      td.className = "slot-cell";
      td.dataset.campKey = campKey;
      td.dataset.section = "Female";
      if (i >= femaleSlotsByCamp[campKey]) {
        td.classList.add("slot-disabled");
        row.appendChild(td);
        return;
      }
      const counselor = campSplit[campKey].female[i];
      if (counselor) {
        td.dataset.occupiedBy = counselor.assignmentId;
        td.appendChild(buildCounselorChip(counselor, state));
      }
      td.addEventListener("dragover", (e) => {
        e.preventDefault();
        td.classList.add("drop-hover");
      });
      td.addEventListener("dragleave", () => td.classList.remove("drop-hover"));
      td.addEventListener("drop", (e) => {
        e.preventDefault();
        td.classList.remove("drop-hover");
        const assignmentId = e.dataTransfer.getData("text/counselor-assignment-id");
        if (!assignmentId) return;
        if (td.dataset.occupiedBy && td.dataset.occupiedBy !== assignmentId) {
          setSectionStatus("counselorStatusWrap", "counselorStatusText", "That slot is already filled. Move to an empty slot or Unassigned first.", true);
          return;
        }
        const counselorObj = state.assignmentById[assignmentId];
        if (!counselorObj || !canDropCounselorToSection(counselorObj, "Female")) {
          setSectionStatus("counselorStatusWrap", "counselorStatusText", "Only female counselors can be dropped into female slots.", true);
          return;
        }
        if (campSplit[campKey].female.length >= femaleSlotsByCamp[campKey] && state.assignmentCampById[assignmentId] !== campKey) {
          setSectionStatus("counselorStatusWrap", "counselorStatusText", `Female slots are full for this camp (${femaleSlotsByCamp[campKey]}).`, true);
          return;
        }
        const changed = moveCounselorBetweenCamps(state, assignmentId, campKey);
        if (changed) {
          renderCounselorLayout(state);
          renderCounselorDashboard(state);
          setSectionStatus("counselorStatusWrap", "counselorStatusText", "Manual counselor move applied in review view.", false);
        }
      });
      row.appendChild(td);
    });
    body.appendChild(row);
  }

  const maleStatusRow = document.createElement("tr");
  maleStatusRow.className = "slot-status-row";
  const maleStatusLabel = document.createElement("td");
  maleStatusLabel.textContent = "Male Status";
  maleStatusRow.appendChild(maleStatusLabel);
  state.campOrder.forEach((campKey) => {
    const td = document.createElement("td");
    td.textContent = statusLabel(campSplit[campKey].male.length, maleSlotsByCamp[campKey]);
    maleStatusRow.appendChild(td);
  });
  body.appendChild(maleStatusRow);

  for (let i = 0; i < maxMaleSlots; i += 1) {
    const row = document.createElement("tr");
    row.className = "slot-row";
    const label = document.createElement("td");
    label.textContent = `Male ${i + 1}`;
    row.appendChild(label);
    state.campOrder.forEach((campKey) => {
      const td = document.createElement("td");
      td.className = "slot-cell";
      td.dataset.campKey = campKey;
      td.dataset.section = "Male";
      if (i >= maleSlotsByCamp[campKey]) {
        td.classList.add("slot-disabled");
        row.appendChild(td);
        return;
      }
      const counselor = campSplit[campKey].male[i];
      if (counselor) {
        td.dataset.occupiedBy = counselor.assignmentId;
        td.appendChild(buildCounselorChip(counselor, state));
      }
      td.addEventListener("dragover", (e) => {
        e.preventDefault();
        td.classList.add("drop-hover");
      });
      td.addEventListener("dragleave", () => td.classList.remove("drop-hover"));
      td.addEventListener("drop", (e) => {
        e.preventDefault();
        td.classList.remove("drop-hover");
        const assignmentId = e.dataTransfer.getData("text/counselor-assignment-id");
        if (!assignmentId) return;
        if (td.dataset.occupiedBy && td.dataset.occupiedBy !== assignmentId) {
          setSectionStatus("counselorStatusWrap", "counselorStatusText", "That slot is already filled. Move to an empty slot or Unassigned first.", true);
          return;
        }
        const counselorObj = state.assignmentById[assignmentId];
        if (!counselorObj || !canDropCounselorToSection(counselorObj, "Male")) {
          setSectionStatus("counselorStatusWrap", "counselorStatusText", "Only male counselors can be dropped into male slots.", true);
          return;
        }
        if (campSplit[campKey].male.length >= maleSlotsByCamp[campKey] && state.assignmentCampById[assignmentId] !== campKey) {
          setSectionStatus("counselorStatusWrap", "counselorStatusText", `Male slots are full for this camp (${maleSlotsByCamp[campKey]}).`, true);
          return;
        }
        const changed = moveCounselorBetweenCamps(state, assignmentId, campKey);
        if (changed) {
          renderCounselorLayout(state);
          renderCounselorDashboard(state);
          setSectionStatus("counselorStatusWrap", "counselorStatusText", "Manual counselor move applied in review view.", false);
        }
      });
      row.appendChild(td);
    });
    body.appendChild(row);
  }

  table.appendChild(body);
  tableWrap.appendChild(table);
  counselorCampLayout.appendChild(tableWrap);
  renderCounselorUnassigned(state);
}

function toGradeEmoji(value) {
  const digits = { 0: "0️⃣", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣" };
  const text = String(value || "").trim();
  if (!text) return "?";
  return text.split("").map((ch) => (Object.prototype.hasOwnProperty.call(digits, ch) ? digits[ch] : ch)).join("");
}

function isDisabilityFlagged(value) {
  const v = String(value == null ? "" : value).trim().toLowerCase();
  if (!v) return false;
  const noValues = new Set(["n/a", "none", "no", "na", "nan", "null", "nat", "undefined"]);
  return !noValues.has(v);
}

function parseRoommateDetail(rawValue) {
  if (Array.isArray(rawValue)) return rawValue;
  if (typeof rawValue === "string" && rawValue.trim()) {
    try {
      const parsed = JSON.parse(rawValue);
      if (Array.isArray(parsed)) return parsed;
    } catch (_) {
      return [];
    }
  }
  return [];
}

function normalizePersonName(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function countEmoji(text, emoji) {
  const matches = String(text || "").match(new RegExp(emoji, "g"));
  return matches ? matches.length : 0;
}

function cabinLabelFromKey(cabinKey) {
  const text = String(cabinKey || "");
  if (!text.includes("|")) return text || "unknown cabin";
  return text.split("|").map((x) => x.trim()).slice(1).join(" | ") || "unknown cabin";
}

function camperFirstNameSortKey(name) {
  const clean = String(name || "").trim().replace(/\s+/g, " ");
  if (!clean) return "";
  const parts = clean.split(" ");
  return (parts[0] || "").toLowerCase();
}

function updateRoommateCounters(state) {
  if (!roommateCounterWrap) return;
  if (!state || !state.camperById) {
    roommateCounterWrap.textContent = "";
    return;
  }
  let green = 0;
  let red = 0;
  let black = 0;
  Object.values(state.camperById).forEach((camper) => {
    if (Array.isArray(camper.roommateLiveDetail) && camper.roommateLiveDetail.length > 0) {
      camper.roommateLiveDetail.forEach((d) => {
        if (d.emoji === "🟢") green += 1;
        else if (d.emoji === "🔴") red += 1;
        else if (d.emoji === "⚫️") black += 1;
      });
      return;
    }
    const fallback = String(camper.roommateFallbackEmojis || "");
    green += countEmoji(fallback, "🟢");
    red += countEmoji(fallback, "🔴");
    black += countEmoji(fallback, "⚫️");
  });
  roommateCounterWrap.textContent = `Roommate totals: 🟢 ${green} | 🔴 ${red} | ⚫️ ${black}`;
}

function updateUndoRedoButtons() {
  if (camperUndoBtn) camperUndoBtn.disabled = cabinHistoryPast.length === 0;
  if (camperRedoBtn) camperRedoBtn.disabled = cabinHistoryFuture.length === 0;
}

function captureCabinSnapshot(state) {
  const snap = {};
  if (!state || !state.cabinOrder) return snap;
  state.cabinOrder.forEach((cabinKey) => {
    const members = (state.cabinsByKey[cabinKey]?.members || []).map((m) => m.camperId);
    snap[cabinKey] = members;
  });
  Object.keys(state.unassignedByWeek || {}).forEach((week) => {
    const key = `__UNASSIGNED__|${week}`;
    snap[key] = (state.unassignedByWeek[week] || []).map((m) => m.camperId);
  });
  return snap;
}

function restoreCabinSnapshot(state, snapshot) {
  if (!state || !snapshot) return;
  const newCamperCabinById = {};
  state.cabinOrder.forEach((cabinKey) => {
    const cabin = state.cabinsByKey[cabinKey];
    const ids = Array.isArray(snapshot[cabinKey]) ? snapshot[cabinKey] : [];
    const restored = [];
    ids.forEach((cid) => {
      const camper = state.camperById[cid];
      if (!camper) return;
      restored.push(camper);
      newCamperCabinById[cid] = cabinKey;
    });
    cabin.members = restored;
  });
  state.unassignedByWeek = {};
  Object.keys(snapshot).forEach((key) => {
    if (!key.startsWith("__UNASSIGNED__|")) return;
    const week = key.replace("__UNASSIGNED__|", "");
    const ids = Array.isArray(snapshot[key]) ? snapshot[key] : [];
    state.unassignedByWeek[week] = ids
      .map((cid) => state.camperById[cid])
      .filter((x) => Boolean(x));
    ids.forEach((cid) => {
      newCamperCabinById[cid] = key;
    });
  });
  Object.keys(state.camperById).forEach((cid) => {
    if (newCamperCabinById[cid]) return;
    const camper = state.camperById[cid];
    const week = String(camper.week || "Week-Unknown");
    const key = `__UNASSIGNED__|${week}`;
    if (!state.unassignedByWeek[week]) state.unassignedByWeek[week] = [];
    state.unassignedByWeek[week].push(camper);
    newCamperCabinById[cid] = key;
  });
  state.camperCabinById = newCamperCabinById;
  recomputeLiveRoommateStatus(state);
  renderCabinLayoutFromState(state);
  renderUnassignedFromState(state);
}

function buildCabinReviewState(rows) {
  const state = {
    cabinsByKey: {},
    cabinOrder: [],
    camperById: {},
    camperCabinById: {},
    weekNameIndex: {},
    unassignedByWeek: {},
  };
  (rows || []).forEach((r, idx) => {
    const week = String(r.Week || "Week-Unknown");
    const cabin = String(r.Cabin || "Unassigned Cabin");
    const cabinKey = `${week} | ${cabin}`;
    if (!state.cabinsByKey[cabinKey]) {
      state.cabinsByKey[cabinKey] = {
        key: cabinKey,
        week,
        cabin,
        gender: String(r["Cabin Gender"] || ""),
        members: [],
      };
      state.cabinOrder.push(cabinKey);
    }
    const camperId = String(r["Camper ID"] || `${week}|${r["Camper Name"] || "Unknown"}|${idx}`);
    const detail = parseRoommateDetail(r["Roommate Status Detail"]).map((d) => ({
      requested: String((d && d.requested) || ""),
      target: String((d && d.target) || ""),
      matched_id: String((d && d.matched_id) || ""),
      emoji: String((d && d.emoji) || ""),
      status: String((d && d.status) || ""),
    }));
    const camper = {
      camperId,
      week,
      name: String(r["Camper Name"] || "Unknown"),
      gender: String(r.Gender || ""),
      grade: r.Grade,
      disabilityFlag: r["Disability Flag"],
      disabilityRaw: r["Disability Raw"],
      roommateRequests: detail,
      roommateFallbackEmojis: String(r["Roommate Status Emojis"] || "").trim(),
      roommateLiveDetail: [],
    };
    state.cabinsByKey[cabinKey].members.push(camper);
    state.camperById[camperId] = camper;
    state.camperCabinById[camperId] = cabinKey;
    const normName = normalizePersonName(camper.name);
    if (normName) {
      if (!state.weekNameIndex[week]) state.weekNameIndex[week] = {};
      state.weekNameIndex[week][normName] = camperId;
    }
  });
  // Backward compatibility: older runs may not include matched_id in detail payload.
  // Resolve by target/requested name in the same week so live emojis can recalculate.
  Object.values(state.cabinsByKey).forEach((cabin) => {
    const weekLookup = state.weekNameIndex[cabin.week] || {};
    cabin.members.forEach((camper) => {
      (camper.roommateRequests || []).forEach((req) => {
        if (req.matched_id) return;
        const targetName = normalizePersonName(req.target || req.requested || "");
        if (targetName && weekLookup[targetName]) {
          req.matched_id = weekLookup[targetName];
        }
      });
    });
  });
  state.cabinOrder.sort();
  return state;
}

function recomputeLiveRoommateStatus(state) {
  if (!state) return;
  Object.values(state.camperById).forEach((camper) => {
    camper.requestedByOthers = false;
  });
  Object.values(state.camperById).forEach((camper) => {
    (camper.roommateRequests || []).forEach((req) => {
      const matchedId = String(req.matched_id || "");
      if (!matchedId) return;
      const target = state.camperById[matchedId];
      if (target) target.requestedByOthers = true;
    });
  });
  Object.values(state.camperById).forEach((camper) => {
    const myCabin = state.camperCabinById[camper.camperId];
    const live = [];
    (camper.roommateRequests || []).forEach((req) => {
      const matchedId = String(req.matched_id || "");
      if (!matchedId) {
        const fallbackEmoji = req.emoji === "🟢" || req.emoji === "🔴" || req.emoji === "⚫️" ? req.emoji : "⚫️";
        live.push({
          emoji: fallbackEmoji,
          target: req.target || req.requested || "unknown",
          status: req.status || "requested camper not found in registration",
        });
        return;
      }
      const targetCamper = state.camperById[matchedId];
      if (targetCamper && camper.gender && targetCamper.gender && camper.gender !== targetCamper.gender) {
        live.push({
          emoji: "⚫️",
          target: req.target || req.requested || "unknown",
          status: "requested camper is a different gender (not a valid roommate match)",
        });
        return;
      }
      const targetCabin = state.camperCabinById[matchedId];
      const myIsCabin = Object.prototype.hasOwnProperty.call(state.cabinsByKey, myCabin);
      const targetIsCabin = Object.prototype.hasOwnProperty.call(state.cabinsByKey, targetCabin);
      if (myIsCabin && targetIsCabin && targetCabin === myCabin) {
        live.push({
          emoji: "🟢",
          target: req.target || req.requested || "unknown",
          status: "request fulfilled",
        });
      } else {
        const cabinLabel = targetCabin ? cabinLabelFromKey(targetCabin) : "unknown cabin";
        live.push({
          emoji: "🔴",
          target: req.target || req.requested || "unknown",
          status: `requested camper assigned to ${cabinLabel}`,
        });
      }
    });
    camper.roommateLiveDetail = live;
  });
}

function moveCamperBetweenCabins(state, camperId, targetCabinKey) {
  if (!state || !camperId || !targetCabinKey) return false;
  const sourceCabinKey = state.camperCabinById[camperId];
  if (!sourceCabinKey || sourceCabinKey === targetCabinKey) return false;
  const source = state.cabinsByKey[sourceCabinKey];
  const target = state.cabinsByKey[targetCabinKey];
  if (!target) return false;
  const camper = state.camperById[camperId];
  if (!camper) return false;
  const sourceWeek = source ? source.week : String(camper.week || "");
  if (sourceWeek !== target.week) {
    setSectionStatus("camperStatusWrap", "camperStatusText", "You can only drag campers between cabins in the same week.", true);
    return false;
  }
  if (source) {
    const idx = source.members.findIndex((m) => m.camperId === camperId);
    if (idx < 0) return false;
    source.members.splice(idx, 1);
  } else {
    const list = state.unassignedByWeek[sourceWeek] || [];
    const idx = list.findIndex((m) => m.camperId === camperId);
    if (idx < 0) return false;
    list.splice(idx, 1);
    state.unassignedByWeek[sourceWeek] = list;
  }
  target.members.push(camper);
  state.camperCabinById[camperId] = targetCabinKey;
  recomputeLiveRoommateStatus(state);
  renderUnassignedFromState(state);
  return true;
}

function appendRoommateEmojisToName(nameSpan, camper) {
  if (Array.isArray(camper.roommateLiveDetail) && camper.roommateLiveDetail.length > 0) {
    const reqSpan = document.createElement("span");
    reqSpan.className = "camper-roommate-status";
    reqSpan.appendChild(document.createTextNode(" "));
    camper.roommateLiveDetail.forEach((d, idx) => {
      if (idx > 0) reqSpan.appendChild(document.createTextNode(" "));
      const em = document.createElement("span");
      em.className = "roommate-emoji";
      em.textContent = d.emoji || "";
      em.title = `${d.target || "unknown"} - ${d.status || "request status"}`;
      reqSpan.appendChild(em);
    });
    nameSpan.appendChild(reqSpan);
  } else if (camper.roommateFallbackEmojis) {
    const reqSpan = document.createElement("span");
    reqSpan.className = "camper-roommate-status";
    reqSpan.appendChild(document.createTextNode(" "));
    const fallback = String(camper.roommateFallbackEmojis || "");
    const tokens = [
      ...Array.from({ length: countEmoji(fallback, "🟢") }, () => "🟢"),
      ...Array.from({ length: countEmoji(fallback, "🔴") }, () => "🔴"),
      ...Array.from({ length: countEmoji(fallback, "⚫️") }, () => "⚫️"),
    ];
    tokens.forEach((emoji, idx) => {
      if (idx > 0) reqSpan.appendChild(document.createTextNode(" "));
      const em = document.createElement("span");
      em.className = "roommate-emoji";
      em.textContent = emoji;
      reqSpan.appendChild(em);
    });
    nameSpan.appendChild(reqSpan);
  }
  if (camper.requestedByOthers) {
    const requested = document.createElement("span");
    requested.className = "roommate-emoji requested-by-emoji";
    requested.textContent = "🟪";
    requested.title = "Requested by another camper";
    nameSpan.appendChild(document.createTextNode(" "));
    nameSpan.appendChild(requested);
  }
}

function addUnassignedToState(unassignedList) {
  if (!cabinReviewState) return;
  const state = cabinReviewState;
  Object.keys(state.unassignedByWeek || {}).forEach((week) => {
    (state.unassignedByWeek[week] || []).forEach((c) => {
      delete state.camperById[c.camperId];
      delete state.camperCabinById[c.camperId];
    });
  });
  state.unassignedByWeek = {};
  (unassignedList || []).forEach((entry, idx) => {
    if (typeof entry === "string") return;
    const week = String(entry.week || "Week-Unknown");
    const camperId = String(entry.camper_id || `${week}|UNASSIGNED|${entry.name || "Unknown"}|${idx}`);
    const detail = parseRoommateDetail(entry.roommate_status_detail).map((d) => ({
      requested: String((d && d.requested) || ""),
      target: String((d && d.target) || ""),
      matched_id: String((d && d.matched_id) || ""),
      emoji: String((d && d.emoji) || ""),
      status: String((d && d.status) || ""),
    }));
    const camper = {
      camperId,
      week,
      name: String(entry.name || "Unknown"),
      gender: String(entry.gender || ""),
      grade: entry.grade,
      disabilityFlag: entry.disability_flag,
      disabilityRaw: entry.disability_flag,
      roommateRequests: detail,
      roommateFallbackEmojis: String(entry.roommate_status_emojis || "").trim(),
      roommateLiveDetail: [],
      unassignedReason: String(entry.reason || ""),
    };
    if (!state.unassignedByWeek[week]) state.unassignedByWeek[week] = [];
    state.unassignedByWeek[week].push(camper);
    state.camperById[camperId] = camper;
    state.camperCabinById[camperId] = `__UNASSIGNED__|${week}`;
  });
}

function renderUnassignedFromState(state) {
  camperUnassignedList.innerHTML = "";
  if (!state) {
    camperUnassignedWrap.classList.add("hidden");
    return;
  }
  const weeks = Object.keys(state.unassignedByWeek || {}).sort();
  const total = weeks.reduce((acc, week) => acc + (state.unassignedByWeek[week] || []).length, 0);
  if (total === 0) {
    camperUnassignedWrap.classList.add("hidden");
    return;
  }
  camperUnassignedWrap.classList.remove("hidden");
  weeks.forEach((week) => {
    const members = [...(state.unassignedByWeek[week] || [])].sort((a, b) => {
      const firstA = camperFirstNameSortKey(a.name);
      const firstB = camperFirstNameSortKey(b.name);
      if (firstA < firstB) return -1;
      if (firstA > firstB) return 1;
      return String(a.name || "").localeCompare(String(b.name || ""));
    });
    if (!members.length) return;
    const weekLi = document.createElement("li");
    weekLi.textContent = `${week}`;
    weekLi.className = "tiny";
    camperUnassignedList.appendChild(weekLi);
    members.forEach((camper) => {
      const li = document.createElement("li");
      li.className = "camper-row";
      li.draggable = true;
      li.dataset.camperId = camper.camperId;
      li.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/camper-id", camper.camperId);
        e.dataTransfer.effectAllowed = "move";
      });
      const nameSpan = document.createElement("span");
      nameSpan.className = "camper-name";
      nameSpan.textContent = camper.name || "Unknown";
      appendRoommateEmojisToName(nameSpan, camper);
      if (isDisabilityFlagged(camper.disabilityFlag)) {
        const fire = document.createElement("span");
        fire.className = "camper-flag";
        fire.textContent = " 🔥";
        fire.title = "Medical flag present";
        nameSpan.appendChild(fire);
      }
      if (camper.unassignedReason) {
        const reasonSpan = document.createElement("span");
        reasonSpan.className = "tiny";
        reasonSpan.textContent = ` - ${camper.unassignedReason}`;
        nameSpan.appendChild(reasonSpan);
      }
      const gradeSpan = document.createElement("span");
      gradeSpan.className = "camper-grade";
      gradeSpan.textContent = camper.grade ? toGradeEmoji(String(camper.grade)) : "?";
      li.appendChild(nameSpan);
      li.appendChild(gradeSpan);
      camperUnassignedList.appendChild(li);
    });
  });
}

function renderCabinLayoutFromState(state) {
  camperCabinLayout.innerHTML = "";
  if (!state || state.cabinOrder.length === 0) {
    camperCabinLayout.textContent = "No cabin rows were generated.";
    updateRoommateCounters(null);
    return;
  }
  updateRoommateCounters(state);

  const help = document.createElement("p");
  help.className = "tiny";
  help.textContent = "Tip: Drag a camper to another cabin (same week). Roommate emojis update live.";
  camperCabinLayout.appendChild(help);

  state.cabinOrder.forEach((cabinKey) => {
    const cabin = state.cabinsByKey[cabinKey];
    const card = document.createElement("div");
    card.className = "cabin-card";
    const title = document.createElement("h4");
    const gender = cabin.gender.toLowerCase();
    if (gender === "female") {
      card.classList.add("cabin-girl");
    } else if (gender === "male") {
      card.classList.add("cabin-boy");
    }
    const count = cabin.members.length;
    title.textContent = `${cabin.key} • ${count} ${count === 1 ? "camper" : "campers"}`;
    card.appendChild(title);

    const list = document.createElement("ul");
    list.dataset.cabinKey = cabinKey;
    list.addEventListener("dragover", (e) => {
      e.preventDefault();
      list.classList.add("drop-hover");
    });
    list.addEventListener("dragleave", () => {
      list.classList.remove("drop-hover");
    });
    list.addEventListener("drop", (e) => {
      e.preventDefault();
      list.classList.remove("drop-hover");
      const camperId = e.dataTransfer.getData("text/camper-id");
      if (!camperId) return;
      const beforeMove = captureCabinSnapshot(state);
      const changed = moveCamperBetweenCabins(state, camperId, cabinKey);
      if (changed) {
        cabinHistoryPast.push(beforeMove);
        cabinHistoryFuture = [];
        updateUndoRedoButtons();
        setSectionStatus("camperStatusWrap", "camperStatusText", "Manual move applied in review view.", false);
        renderCabinLayoutFromState(state);
      }
    });

    const sortedMembers = [...cabin.members].sort((a, b) => {
      const firstA = camperFirstNameSortKey(a.name);
      const firstB = camperFirstNameSortKey(b.name);
      if (firstA < firstB) return -1;
      if (firstA > firstB) return 1;
      const nameA = String(a.name || "").toLowerCase();
      const nameB = String(b.name || "").toLowerCase();
      if (nameA < nameB) return -1;
      if (nameA > nameB) return 1;
      return 0;
    });

    sortedMembers.forEach((r) => {
      const li = document.createElement("li");
      li.className = "camper-row";
      li.draggable = true;
      li.dataset.camperId = r.camperId;
      li.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/camper-id", r.camperId);
        e.dataTransfer.effectAllowed = "move";
      });

      const nameSpan = document.createElement("span");
      nameSpan.className = "camper-name";
      nameSpan.textContent = `${r.name || "Unknown"}`;
      appendRoommateEmojisToName(nameSpan, r);

      if (isDisabilityFlagged(r.disabilityFlag)) {
        const fire = document.createElement("span");
        fire.className = "camper-flag";
        fire.textContent = " 🔥";
        const raw = String(r.disabilityRaw == null ? "" : r.disabilityRaw).trim();
        fire.title = raw ? `Medical note: ${raw}` : "Medical flag present";
        nameSpan.appendChild(fire);
      }
      const gradeSpan = document.createElement("span");
      gradeSpan.className = "camper-grade";
      gradeSpan.textContent = toGradeEmoji(String(r.grade === "" || r.grade == null ? "?" : r.grade));
      li.appendChild(nameSpan);
      li.appendChild(gradeSpan);
      list.appendChild(li);
    });
    card.appendChild(list);
    camperCabinLayout.appendChild(card);
  });
}

function renderCabinLayout(rows) {
  cabinReviewState = buildCabinReviewState(rows);
  cabinHistoryPast = [];
  cabinHistoryFuture = [];
  updateUndoRedoButtons();
  recomputeLiveRoommateStatus(cabinReviewState);
  renderCabinLayoutFromState(cabinReviewState);
}

function renderUnassigned(list) {
  if (!cabinReviewState) {
    camperUnassignedList.innerHTML = "";
    camperUnassignedWrap.classList.add("hidden");
    return;
  }
  addUnassignedToState(list || []);
  recomputeLiveRoommateStatus(cabinReviewState);
  updateRoommateCounters(cabinReviewState);
  renderUnassignedFromState(cabinReviewState);
}

function resetMappingState() {
  document.getElementById("camperMappingWrap").classList.add("hidden");
  document.getElementById("counselorMappingWrap").classList.add("hidden");
  document.getElementById("camperMappingWrap").innerHTML = "";
  document.getElementById("counselorMappingWrap").innerHTML = "";
  document.getElementById("camperRunBtn").classList.add("hidden");
  document.getElementById("counselorRunBtn").classList.add("hidden");
  document.getElementById("counselorDownloadLink").classList.add("hidden");
  if (counselorReviewWrap) counselorReviewWrap.classList.add("hidden");
  if (counselorCampLayout) counselorCampLayout.innerHTML = "";
  if (counselorDashboardWrap) counselorDashboardWrap.innerHTML = "";
  if (counselorRequestCounterWrap) counselorRequestCounterWrap.textContent = "";
  if (counselorUnassignedWrap) counselorUnassignedWrap.classList.add("hidden");
  if (counselorUnassignedList) counselorUnassignedList.innerHTML = "";
  if (counselorSingleCampOnly) counselorSingleCampOnly.checked = false;
  if (counselorRedCount) counselorRedCount.textContent = "🔴 0";
  if (counselorGreenCount) counselorGreenCount.textContent = "🟢 0";
  if (counselorBlackCount) counselorBlackCount.textContent = "⚫️ 0";
  if (counselorPurpleCount) counselorPurpleCount.textContent = "🟪 0";
  if (counselorLoadWrap) counselorLoadWrap.classList.add("hidden");
  if (counselorLoadFemaleList) counselorLoadFemaleList.innerHTML = "";
  if (counselorLoadMaleList) counselorLoadMaleList.innerHTML = "";
  camperReviewWrap.classList.add("hidden");
  camperExportBtn.classList.add("hidden");
  camperCabinLayout.innerHTML = "";
  camperUnassignedWrap.classList.add("hidden");
  camperUnassignedList.innerHTML = "";
  if (roommateCounterWrap) roommateCounterWrap.textContent = "";
  lastCamperMapping = null;
  cabinReviewState = null;
  cabinHistoryPast = [];
  cabinHistoryFuture = [];
  counselorReviewState = null;
  updateUndoRedoButtons();
}

function buildSharedFormData() {
  const file = sharedInputFile.files && sharedInputFile.files[0];
  if (!file) throw new Error("Please upload a file first in Shared Upload.");
  const data = new FormData();
  data.append("input_file", file);
  const cfg = sharedConfigFile.files && sharedConfigFile.files[0];
  if (cfg) data.append("config_file", cfg);
  const campParamsEl = document.getElementById("counselorCampParameters");
  if (campParamsEl && String(campParamsEl.value || "").trim()) {
    data.append("camp_parameters_text", String(campParamsEl.value || "").trim());
  }
  data.append("settings_overrides_json", JSON.stringify(currentSettings || {}));
  if (counselorSingleCampOnly) {
    data.append("single_camp_only", counselorSingleCampOnly.checked ? "true" : "false");
  }
  return data;
}

async function runCamperAssignment(mapping, statusWrapId, statusTextId, runBtn = null) {
  if (runBtn) {
    runBtn.disabled = true;
  }
  setSectionStatus(statusWrapId, statusTextId, "Running assignment...", false);
  clearWarnings();
  try {
    const formData = buildSharedFormData();
    formData.append("mapping_json", JSON.stringify(mapping || {}));
    const response = await fetch("/api/run/campers", { method: "POST", body: formData });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Assignment failed.");
    renderWarnings(result.warnings || []);
    renderMetrics(result.metrics || []);
    renderCounselorLoadStatus([]);
    camperReviewWrap.classList.remove("hidden");
    camperExportBtn.href = `/api/download/${result.run_id}`;
    camperExportBtn.classList.remove("hidden");
    renderCabinLayout(result.cabin_layout || []);
    renderUnassigned(result.unassigned_names || []);
    setSectionStatus(statusWrapId, statusTextId, "Assignment complete.", false);
  } catch (err) {
    setSectionStatus(statusWrapId, statusTextId, err.message || "Something went wrong.", true);
  } finally {
    if (runBtn) runBtn.disabled = false;
  }
}

async function wireForm({
  inspectBtnId,
  runBtnId,
  mappingWrapId,
  downloadLinkId,
  statusWrapId,
  statusTextId,
  inspectEndpoint,
  runEndpoint,
  renderMapping,
  mappingFromUI,
  onSuccess,
}) {
  const inspectBtn = document.getElementById(inspectBtnId);
  const runBtn = document.getElementById(runBtnId);
  const mappingWrap = document.getElementById(mappingWrapId);
  const downloadLink = downloadLinkId ? document.getElementById(downloadLinkId) : null;
  let inspected = false;

  inspectBtn.addEventListener("click", async () => {
    inspectBtn.disabled = true;
    const oldText = inspectBtn.textContent;
    inspectBtn.textContent = "Analyzing...";
    setSectionStatus(statusWrapId, statusTextId, "Reading file and suggesting fields...", false);
    try {
      const inspectForm = buildSharedFormData();
      const response = await fetch(inspectEndpoint, { method: "POST", body: inspectForm });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Could not inspect fields.");
      renderMapping(mappingWrap, result.mapping);
      runBtn.classList.remove("hidden");
      inspected = true;
      setSectionStatus(statusWrapId, statusTextId, "Field suggestions ready. Review and run.", false);
    } catch (err) {
      setSectionStatus(statusWrapId, statusTextId, err.message || "Could not inspect.", true);
    } finally {
      inspectBtn.disabled = false;
      inspectBtn.textContent = oldText;
    }
  });

  runBtn.addEventListener("click", async () => {
    if (!inspected) {
      setSectionStatus(statusWrapId, statusTextId, "Please click 'Step 2 - Match Fields' first.", true);
      return;
    }
    const mapping = mappingFromUI();
    if (runEndpoint === "/api/run/campers") {
      lastCamperMapping = mapping;
      await runCamperAssignment(mapping, statusWrapId, statusTextId, runBtn);
      return;
    }
    runBtn.disabled = true;
    const oldText = runBtn.textContent;
    runBtn.textContent = "Running...";
    if (downloadLink) downloadLink.classList.add("hidden");
    setSectionStatus(statusWrapId, statusTextId, "Running assignment...", false);
    clearWarnings();
    try {
      const formData = buildSharedFormData();
      formData.append("mapping_json", JSON.stringify(mapping));
      const response = await fetch(runEndpoint, { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Assignment failed.");
      setSectionStatus(statusWrapId, statusTextId, "Assignment complete.", false);
      if (downloadLink) {
        downloadLink.href = `/api/download/${result.run_id}`;
        downloadLink.classList.remove("hidden");
      }
      renderWarnings(result.warnings || []);
      renderMetrics(result.metrics || []);
      if (onSuccess) onSuccess(result, { mappingWrap, runBtn });
    } catch (err) {
      setSectionStatus(statusWrapId, statusTextId, err.message || "Something went wrong.", true);
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = oldText;
    }
  });
}

async function loadDefaults() {
  const res = await fetch("/api/default-settings");
  const json = await res.json();
  if (!res.ok || !json.ok) throw new Error(json.error || "Could not load default settings.");
  defaultSettings = json.settings;
  currentSettings = JSON.parse(JSON.stringify(defaultSettings));
  fillSettingsForm(currentSettings);
}

function handleCounselorRunSuccess(result) {
  counselorReviewState = buildCounselorReviewState(result.review || {});
  recomputeCounselorFriendStatus(counselorReviewState);
  updateCounselorRequestCounters(counselorReviewState);
  renderCounselorLoadStatus(buildCounselorLoadRowsFromState(counselorReviewState));
  if (counselorReviewWrap) counselorReviewWrap.classList.remove("hidden");
  renderCounselorDashboard(counselorReviewState);
  renderCounselorLayout(counselorReviewState);
}

wireForm({
  inspectBtnId: "camperInspectBtn",
  runBtnId: "camperRunBtn",
  mappingWrapId: "camperMappingWrap",
  downloadLinkId: null,
  statusWrapId: "camperStatusWrap",
  statusTextId: "camperStatusText",
  inspectEndpoint: "/api/inspect/campers",
  runEndpoint: "/api/run/campers",
  renderMapping: renderCamperMapping,
  mappingFromUI: camperMappingFromUI,
});

wireForm({
  inspectBtnId: "counselorInspectBtn",
  runBtnId: "counselorRunBtn",
  mappingWrapId: "counselorMappingWrap",
  downloadLinkId: "counselorDownloadLink",
  statusWrapId: "counselorStatusWrap",
  statusTextId: "counselorStatusText",
  inspectEndpoint: "/api/inspect/counselors",
  runEndpoint: "/api/run/counselors",
  renderMapping: renderCounselorMapping,
  mappingFromUI: counselorMappingFromUI,
  onSuccess: handleCounselorRunSuccess,
});

function init() {
  clearWarnings();
  metricsCard.classList.add("hidden");
  warningsCard.classList.add("hidden");
  showTab("results");
  tabResultsBtn.addEventListener("click", () => showTab("results"));
  tabSettingsBtn.addEventListener("click", () => showTab("settings"));
  settingsBackBtn.addEventListener("click", () => showTab("results"));
  camperSettingsBtn.addEventListener("click", () => showTab("settings"));

  saveSettingsBtn.addEventListener("click", () => {
    currentSettings = collectSettingsFromForm();
    setSettingsStatus("Settings saved. Go back and re-run.");
  });

  resetSettingsBtn.addEventListener("click", () => {
    if (!defaultSettings) return;
    currentSettings = JSON.parse(JSON.stringify(defaultSettings));
    fillSettingsForm(currentSettings);
    setSettingsStatus("Defaults restored.");
  });

  sharedInputFile.addEventListener("change", resetMappingState);
  sharedConfigFile.addEventListener("change", resetMappingState);
  camperBackBtn.addEventListener("click", () => {
    camperReviewWrap.classList.add("hidden");
    document.getElementById("camperMappingWrap").scrollIntoView({ behavior: "smooth" });
  });
  if (counselorBackBtn) {
    counselorBackBtn.addEventListener("click", () => {
      if (counselorReviewWrap) counselorReviewWrap.classList.add("hidden");
      document.getElementById("counselorMappingWrap").scrollIntoView({ behavior: "smooth" });
    });
  }
  if (camperUndoBtn) {
    camperUndoBtn.addEventListener("click", () => {
      if (!cabinReviewState || cabinHistoryPast.length === 0) return;
      const current = captureCabinSnapshot(cabinReviewState);
      const previous = cabinHistoryPast.pop();
      cabinHistoryFuture.push(current);
      restoreCabinSnapshot(cabinReviewState, previous);
      updateUndoRedoButtons();
      setSectionStatus("camperStatusWrap", "camperStatusText", "Undid last cabin move.", false);
    });
  }
  if (camperRedoBtn) {
    camperRedoBtn.addEventListener("click", () => {
      if (!cabinReviewState || cabinHistoryFuture.length === 0) return;
      const current = captureCabinSnapshot(cabinReviewState);
      const next = cabinHistoryFuture.pop();
      cabinHistoryPast.push(current);
      restoreCabinSnapshot(cabinReviewState, next);
      updateUndoRedoButtons();
      setSectionStatus("camperStatusWrap", "camperStatusText", "Redid cabin move.", false);
    });
  }
  camperRerunBtn.addEventListener("click", async () => {
    if (!lastCamperMapping) {
      setSectionStatus("camperStatusWrap", "camperStatusText", "Run once first so mapping is available.", true);
      return;
    }
    await runCamperAssignment(lastCamperMapping, "camperStatusWrap", "camperStatusText", camperRerunBtn);
  });
  camperRestartBtn.addEventListener("click", () => {
    sharedInputFile.value = "";
    sharedConfigFile.value = "";
    resetMappingState();
    setSectionStatus("camperStatusWrap", "camperStatusText", "Restarted. Upload and map again.", false);
  });

  loadDefaults().catch((err) => {
    setSettingsStatus(err.message || "Could not load settings.", true);
  });
}

init();
