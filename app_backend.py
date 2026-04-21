#!/usr/bin/env python3
import io
import json
import re
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file
from rapidfuzz import fuzz

from assign_tool import (
    assign_campers,
    assign_counselors,
    is_available_for_camp,
    parse_camper_rows,
    parse_capacity,
    preference_rank,
    split_availability_list,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = APP_DIR / "config.template.json"

app = Flask(__name__)
RESULTS = {}

CAMPER_FIELD_ALIASES = {
    "week_column": ["week", "session", "camp week"],
    "first_name": ["first name", "firstname", "given name"],
    "last_name": ["last name", "lastname", "surname", "family name"],
    "gender": ["gender", "sex"],
    "grade": ["grade", "current grade", "spring grade"],
    "date_of_birth": ["date of birth", "dob", "birth date", "birthday"],
    "school": ["school", "school name"],
    "disability_flag": ["disability", "disability support", "special needs", "support needs"],
    "roommate_requests": ["roommate requests", "roommate request", "friends", "cabin mate requests"],
}

COUNSELOR_FIELD_ALIASES = {
    "first_name": ["first name", "firstname", "given name"],
    "last_name": ["last name", "lastname", "surname"],
    "gender": ["gender", "sex"],
    "email": ["email", "email address"],
    "availability": ["available camps", "availability", "check all camps"],
    "preference_1": ["top choice 1", "1st choice", "first choice", "most desired camp"],
    "preference_2": ["top choice 2", "2nd choice", "second choice"],
    "preference_3": ["top choice 3", "3rd choice", "third choice"],
    "willing_camps": ["willing camps", "how many camps", "as many as needed"],
    "friend_requests": ["friend requests", "friend names", "volunteer with"],
}

TARGET_FIELD_ALIASES = {
    "camp": ["camp", "camp name"],
    "target_total": ["target total", "total", "needed", "slots"],
    "target_female": ["target female", "female", "girls needed"],
    "target_male": ["target male", "male", "boys needed"],
}

COUNSELOR_FIXED_FEMALE_SLOTS = 12
COUNSELOR_FIXED_MALE_SLOTS = 9


def load_default_config() -> dict:
    with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_template_workbook_bytes(
    config: dict, include_campers: bool, include_counselors: bool, include_targets: bool
) -> bytes:
    campers_headers = list(
        {
            config["week_column"],
            config["campers"]["first_name"],
            config["campers"]["last_name"],
            config["campers"]["gender"],
            config["campers"]["grade"],
            config["campers"]["date_of_birth"],
            config["campers"]["school"],
            config["campers"]["disability_flag"],
            config["campers"]["roommate_requests"],
        }
    )
    counselors_headers = list(
        {
            config["counselors"]["first_name"],
            config["counselors"]["last_name"],
            config["counselors"]["gender"],
            config["counselors"]["email"],
            config["counselors"]["availability"],
            config["counselors"]["preference_1"],
            config["counselors"]["preference_2"],
            config["counselors"]["preference_3"],
            config["counselors"].get("willing_camps", "Willing Camps"),
            config["counselors"]["friend_requests"],
        }
    )
    camp_targets_headers = ["Camp", "Target Total", "Target Female", "Target Male"]

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        if include_campers:
            pd.DataFrame(columns=campers_headers).to_excel(
                writer, index=False, sheet_name=config["campers_sheet"]
            )
        if include_counselors:
            pd.DataFrame(columns=counselors_headers).to_excel(
                writer, index=False, sheet_name=config["counselors_sheet"]
            )
        if include_targets:
            pd.DataFrame(columns=camp_targets_headers).to_excel(
                writer, index=False, sheet_name=config["camp_targets_sheet"]
            )
    return buffer.getvalue()


def parse_config(uploaded_config_file) -> dict:
    if uploaded_config_file is None:
        return load_default_config()
    return json.loads(uploaded_config_file.read().decode("utf-8"))


def deep_merge_dict(base: dict, overrides: dict) -> dict:
    merged = json.loads(json.dumps(base))
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _norm(text: str) -> str:
    return str(text).strip().lower()


def similarity_score(a: str, b: str) -> float:
    a_norm = _norm(a)
    b_norm = _norm(b)
    if not a_norm or not b_norm:
        return 0.0
    base = max(
        fuzz.ratio(a_norm, b_norm),
        fuzz.partial_ratio(a_norm, b_norm),
        fuzz.token_set_ratio(a_norm, b_norm),
    )
    if a_norm == b_norm:
        base += 15
    elif a_norm in b_norm or b_norm in a_norm:
        base += 8
    return float(base)


def suggest_column(columns: List[str], aliases: List[str], fallback: str) -> str:
    if not columns:
        return ""
    candidates = aliases + [fallback]
    best_col = columns[0]
    best_score = -1.0
    for col in columns:
        local_best = 0.0
        for cand in candidates:
            local_best = max(local_best, similarity_score(cand, col))
        if local_best > best_score:
            best_score = local_best
            best_col = col
    return best_col


def split_camp_tokens(text: str) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    raw = re.sub(r"[\r\n]+", ",", raw)
    parts = re.split(r"[,;/|]|\band\b|&", raw, flags=re.IGNORECASE)
    out = []
    for part in parts:
        p = str(part).strip()
        if p:
            out.append(p)
    return out


def extract_camp_sessions_from_text(text: str) -> List[str]:
    raw = str(text or "")
    if not raw:
        return []
    matches = re.findall(
        r"\b(sky camp|sky games|western adventure camp|western camp|sc|sg|wac|wc)\s*(?:session|sess|s)?\s*[-:]?\s*(\d+)\b",
        raw,
        flags=re.IGNORECASE,
    )
    family_map = {
        "sky camp": "SKY Camp",
        "sky games": "SKY Games",
        "western adventure camp": "Western Camp",
        "western camp": "Western Camp",
        "sc": "SKY Camp",
        "sg": "SKY Games",
        "wac": "Western Camp",
        "wc": "Western Camp",
    }
    out: List[str] = []
    seen = set()
    for fam, num in matches:
        fam_key = str(fam).strip().lower()
        canonical = f"{family_map.get(fam_key, str(fam).strip())} Session {str(num).strip()}"
        key = _norm(canonical)
        if key in seen:
            continue
        seen.add(key)
        out.append(canonical)
    return out


def parse_camp_parameters(text: str) -> Dict[str, List[str]]:
    catalog: Dict[str, List[str]] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" in line:
            left, right = line.split("=", 1)
            alias = left.strip()
            canonical = right.strip() or alias
        else:
            alias = line
            canonical = line
        if not canonical:
            continue
        if canonical not in catalog:
            catalog[canonical] = []
        for candidate in [canonical, alias]:
            c = str(candidate).strip()
            if c and c not in catalog[canonical]:
                catalog[canonical].append(c)
    return catalog


def canonical_session_name(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    m = re.search(
        r"\b(sky camp|sky games|western adventure camp|western camp|sc|sg|wac|wc)\s*(?:session|sess|s)?\s*[-:]?\s*(\d+)\b",
        raw,
        flags=re.IGNORECASE,
    )
    if not m:
        return raw
    family_raw = m.group(1).lower()
    session_num = m.group(2)
    family_map = {
        "sky camp": "SKY Camp",
        "sky games": "SKY Games",
        "western adventure camp": "Western Camp",
        "western camp": "Western Camp",
        "sc": "SKY Camp",
        "sg": "SKY Games",
        "wac": "Western Camp",
        "wc": "Western Camp",
    }
    family = family_map.get(family_raw, m.group(1).strip())
    return f"{family} Session {session_num}"


def parse_camp_parameter_order(text: str) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" in line:
            _, right = line.split("=", 1)
            canonical = right.strip()
        else:
            canonical = line
        canonical = canonical_session_name(canonical)
        key = _norm(canonical)
        if not canonical or key in seen:
            continue
        seen.add(key)
        ordered.append(canonical)
    return ordered


def best_match_camp_name(value: str, catalog: Dict[str, List[str]], threshold: float = 76.0) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not catalog:
        return raw
    raw_norm = _norm(raw)
    for canonical, aliases in catalog.items():
        if raw_norm == _norm(canonical):
            return canonical
        for alias in aliases:
            if raw_norm == _norm(alias):
                return canonical
    def camp_number(text: str) -> str:
        m = re.search(r"\b(?:session|sess|s|camp|games)\s*[-:]?\s*(\d+)\b", _norm(text))
        return m.group(1) if m else ""

    def camp_family(text: str) -> str:
        t = _norm(text)
        if re.search(r"\b(sky\s*games|sg)\b", t):
            return "sky games"
        if re.search(r"\b(western\s*adventure\s*camp|western\s*camp|wac|wc)\b", t):
            return "western camp"
        if re.search(r"\b(sky\s*camp|sc)\b", t):
            return "sky camp"
        return ""

    raw_num = camp_number(raw)
    raw_family = camp_family(raw)
    best_canonical = raw
    best_score = 0.0
    for canonical, aliases in catalog.items():
        canonical_num = camp_number(canonical)
        canonical_family = camp_family(canonical)
        if raw_num and canonical_num and raw_num != canonical_num:
            continue
        if raw_family and canonical_family and raw_family != canonical_family:
            continue
        local_best = similarity_score(raw, canonical)
        # Strongly boost exact family+session matches even when long date ranges exist.
        if raw_num and canonical_num and raw_num == canonical_num:
            local_best += 20
        if raw_family and canonical_family and raw_family == canonical_family:
            local_best += 20
        for alias in aliases:
            alias_num = camp_number(alias)
            alias_family = camp_family(alias)
            if raw_num and alias_num and raw_num != alias_num:
                continue
            if raw_family and alias_family and raw_family != alias_family:
                continue
            alias_score = similarity_score(raw, alias)
            if raw_num and alias_num and raw_num == alias_num:
                alias_score += 20
            if raw_family and alias_family and raw_family == alias_family:
                alias_score += 20
            local_best = max(local_best, alias_score)
        if local_best > best_score:
            best_score = local_best
            best_canonical = canonical
    return best_canonical if best_score >= threshold else raw


def normalize_camp_list_text(value: str, catalog: Dict[str, List[str]]) -> str:
    direct_sessions = extract_camp_sessions_from_text(value)
    tokens = direct_sessions or split_camp_tokens(value)
    if not tokens:
        return ""
    mapped = []
    seen = set()
    for token in tokens:
        canonical = best_match_camp_name(token, catalog)
        key = _norm(canonical)
        if not canonical or key in seen:
            continue
        seen.add(key)
        mapped.append(canonical)
    return ", ".join(mapped)


def detect_sheet_for_aliases(
    sheets_to_columns: Dict[str, List[str]], aliases_map: Dict[str, List[str]]
) -> str:
    best_sheet = ""
    best_score = -1
    for sheet, cols in sheets_to_columns.items():
        score = 0.0
        for _, aliases in aliases_map.items():
            field_best = 0.0
            for col in cols:
                for alias in aliases:
                    field_best = max(field_best, similarity_score(alias, col))
            score += field_best
        if score > best_score:
            best_score = score
            best_sheet = sheet
    return best_sheet


def read_tables_from_upload(file_bytes: bytes, filename: str) -> Tuple[str, Dict[str, pd.DataFrame]]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes))
        return "csv", {"csv": df}
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        tables = {sheet: pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet) for sheet in xls.sheet_names}
        return "excel", tables
    raise ValueError("Unsupported file type. Please upload .xlsx or .csv")


def build_camper_mapping_suggestions(
    config: dict, file_type: str, tables: Dict[str, pd.DataFrame]
) -> dict:
    sheets_to_columns = {name: list(df.columns) for name, df in tables.items()}
    default_sheet = "csv" if file_type == "csv" else detect_sheet_for_aliases(sheets_to_columns, CAMPER_FIELD_ALIASES)
    if not default_sheet:
        default_sheet = next(iter(sheets_to_columns.keys()))
    cols = sheets_to_columns.get(default_sheet, [])
    campers_cfg = config["campers"]
    suggestions = {
        "week_column": suggest_column(cols, CAMPER_FIELD_ALIASES["week_column"], config["week_column"]),
        "first_name": suggest_column(cols, CAMPER_FIELD_ALIASES["first_name"], campers_cfg["first_name"]),
        "last_name": suggest_column(cols, CAMPER_FIELD_ALIASES["last_name"], campers_cfg["last_name"]),
        "gender": suggest_column(cols, CAMPER_FIELD_ALIASES["gender"], campers_cfg["gender"]),
        "grade": suggest_column(cols, CAMPER_FIELD_ALIASES["grade"], campers_cfg["grade"]),
        "date_of_birth": suggest_column(cols, CAMPER_FIELD_ALIASES["date_of_birth"], campers_cfg["date_of_birth"]),
        "school": suggest_column(cols, CAMPER_FIELD_ALIASES["school"], campers_cfg["school"]),
        "disability_flag": suggest_column(cols, CAMPER_FIELD_ALIASES["disability_flag"], campers_cfg["disability_flag"]),
        "roommate_requests": suggest_column(cols, CAMPER_FIELD_ALIASES["roommate_requests"], campers_cfg["roommate_requests"]),
    }
    return {
        "file_type": file_type,
        "sheets": list(sheets_to_columns.keys()),
        "columns_by_sheet": sheets_to_columns,
        "suggested": {
            "sheet": default_sheet,
            "fields": suggestions,
        },
    }


def build_counselor_mapping_suggestions(
    config: dict, file_type: str, tables: Dict[str, pd.DataFrame]
) -> dict:
    sheets_to_columns = {name: list(df.columns) for name, df in tables.items()}
    if file_type == "csv":
        default_counselor_sheet = "csv"
        default_target_sheet = "csv"
    else:
        default_counselor_sheet = detect_sheet_for_aliases(sheets_to_columns, COUNSELOR_FIELD_ALIASES)
        default_target_sheet = detect_sheet_for_aliases(sheets_to_columns, TARGET_FIELD_ALIASES)
        if not default_counselor_sheet:
            default_counselor_sheet = next(iter(sheets_to_columns.keys()))
        if not default_target_sheet:
            default_target_sheet = next(iter(sheets_to_columns.keys()))

    c_cols = sheets_to_columns.get(default_counselor_sheet, [])
    t_cols = sheets_to_columns.get(default_target_sheet, [])
    counselors_cfg = config["counselors"]
    suggestions = {
        "counselor_sheet": default_counselor_sheet,
        "target_sheet": default_target_sheet,
        "counselor_fields": {
            "first_name": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["first_name"], counselors_cfg["first_name"]),
            "last_name": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["last_name"], counselors_cfg["last_name"]),
            "gender": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["gender"], counselors_cfg["gender"]),
            "email": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["email"], counselors_cfg["email"]),
            "availability": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["availability"], counselors_cfg["availability"]),
            "preference_1": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["preference_1"], counselors_cfg["preference_1"]),
            "preference_2": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["preference_2"], counselors_cfg["preference_2"]),
            "preference_3": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["preference_3"], counselors_cfg["preference_3"]),
            "willing_camps": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["willing_camps"], counselors_cfg["willing_camps"]),
            "friend_requests": suggest_column(c_cols, COUNSELOR_FIELD_ALIASES["friend_requests"], counselors_cfg["friend_requests"]),
        },
        "target_fields": {
            "camp": suggest_column(t_cols, TARGET_FIELD_ALIASES["camp"], "Camp"),
            "target_total": suggest_column(t_cols, TARGET_FIELD_ALIASES["target_total"], "Target Total"),
            "target_female": suggest_column(t_cols, TARGET_FIELD_ALIASES["target_female"], "Target Female"),
            "target_male": suggest_column(t_cols, TARGET_FIELD_ALIASES["target_male"], "Target Male"),
        },
    }
    return {
        "file_type": file_type,
        "sheets": list(sheets_to_columns.keys()),
        "columns_by_sheet": sheets_to_columns,
        "suggested": suggestions,
    }


def apply_camper_mapping_to_config(config: dict, mapping: dict) -> dict:
    cfg = json.loads(json.dumps(config))
    sheet = mapping.get("sheet")
    if sheet and sheet != "csv":
        cfg["campers_sheet"] = sheet
    fields = mapping.get("fields", {})
    if "week_column" in fields:
        cfg["week_column"] = fields["week_column"]
    for key in cfg["campers"].keys():
        if key in fields:
            cfg["campers"][key] = fields[key]
    return cfg


def apply_counselor_mapping_to_config(config: dict, mapping: dict) -> dict:
    cfg = json.loads(json.dumps(config))
    c_sheet = mapping.get("counselor_sheet")
    t_sheet = mapping.get("target_sheet")
    if c_sheet and c_sheet != "csv":
        cfg["counselors_sheet"] = c_sheet
    if t_sheet and t_sheet != "csv":
        cfg["camp_targets_sheet"] = t_sheet
    c_fields = mapping.get("counselor_fields", {})
    for key in cfg["counselors"].keys():
        if key in c_fields:
            cfg["counselors"][key] = c_fields[key]
    return cfg


def normalize_targets_df(target_df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    tf = mapping.get("target_fields", {})
    out = pd.DataFrame()
    out["Camp"] = target_df.get(tf.get("camp", "Camp"), "")
    out["Target Total"] = target_df.get(tf.get("target_total", "Target Total"), 0)
    out["Target Female"] = target_df.get(tf.get("target_female", "Target Female"), 0)
    out["Target Male"] = target_df.get(tf.get("target_male", "Target Male"), 0)
    return out


def export_status_label(assigned: int, target: int) -> str:
    left = max(0, int(target) - int(assigned))
    if left == 0:
        return "FULL"
    if left == 1:
        return "1 LEFT"
    return f"{left} LEFT"


def build_counselor_layout_df(
    assignments_df: pd.DataFrame, camp_targets_df: pd.DataFrame, camp_order: List[str]
) -> pd.DataFrame:
    camps = [str(c).strip() for c in (camp_order or []) if str(c).strip()]
    if not camps:
        camps = (
            camp_targets_df.get("Camp", pd.Series(dtype=str))
            .fillna("")
            .astype(str)
            .str.strip()
            .tolist()
        )
        camps = [c for i, c in enumerate(camps) if c and c not in camps[:i]]

    target_by_camp = {}
    for camp in camps:
        target_by_camp[camp] = {"female": 12, "male": 9}
    if not camp_targets_df.empty:
        target_work = camp_targets_df.copy()
        target_work["Camp"] = target_work["Camp"].fillna("").astype(str).str.strip()
        for col in ["Target Female", "Target Male"]:
            target_work[col] = pd.to_numeric(target_work[col], errors="coerce").fillna(0).astype(int)
        target_work = target_work[target_work["Camp"] != ""]
        grouped = (
            target_work.groupby("Camp", as_index=False)[["Target Female", "Target Male"]]
            .sum()
        )
        for _, row in grouped.iterrows():
            camp = str(row.get("Camp", "")).strip()
            if not camp:
                continue
            target_by_camp[camp] = {
                "female": max(0, int(row.get("Target Female", 0))),
                "male": max(0, int(row.get("Target Male", 0))),
            }
            if camp not in camps:
                camps.append(camp)

    female_by_camp = {camp: [] for camp in camps}
    male_by_camp = {camp: [] for camp in camps}
    if not assignments_df.empty:
        work = assignments_df.copy()
        work["Camp"] = work["Camp"].fillna("").astype(str).str.strip()
        work["Counselor Name"] = work["Counselor Name"].fillna("").astype(str).str.strip()
        work["Gender"] = work["Gender"].fillna("").astype(str).str.strip()
        work["Preference Match"] = work["Preference Match"].fillna("").astype(str).str.strip()
        for _, row in work.iterrows():
            camp = str(row.get("Camp", "")).strip()
            if camp not in female_by_camp:
                female_by_camp[camp] = []
                male_by_camp[camp] = []
                target_by_camp.setdefault(camp, {"female": 0, "male": 0})
                camps.append(camp)
            name = str(row.get("Counselor Name", "")).strip() or "Unknown"
            pref = str(row.get("Preference Match", "")).strip()
            label = f"{name} P{pref}" if pref in {"1", "2", "3"} else name
            gender = str(row.get("Gender", "")).strip().lower()
            if gender.startswith("f"):
                female_by_camp[camp].append(label)
            elif gender.startswith("m"):
                male_by_camp[camp].append(label)
            else:
                female_by_camp[camp].append(label)

    for camp in camps:
        female_by_camp[camp] = sorted(female_by_camp.get(camp, []), key=lambda x: x.lower())
        male_by_camp[camp] = sorted(male_by_camp.get(camp, []), key=lambda x: x.lower())

    max_female = max([target_by_camp.get(c, {}).get("female", 0) for c in camps] + [0])
    max_male = max([target_by_camp.get(c, {}).get("male", 0) for c in camps] + [0])

    rows = []
    female_status_row = {"Slot": "Female Status"}
    for camp in camps:
        female_status_row[camp] = export_status_label(
            len(female_by_camp.get(camp, [])),
            target_by_camp.get(camp, {}).get("female", 0),
        )
    rows.append(female_status_row)
    for idx in range(max_female):
        row = {"Slot": f"Female {idx + 1}"}
        for camp in camps:
            members = female_by_camp.get(camp, [])
            row[camp] = members[idx] if idx < len(members) else ""
        rows.append(row)

    male_status_row = {"Slot": "Male Status"}
    for camp in camps:
        male_status_row[camp] = export_status_label(
            len(male_by_camp.get(camp, [])),
            target_by_camp.get(camp, {}).get("male", 0),
        )
    rows.append(male_status_row)
    for idx in range(max_male):
        row = {"Slot": f"Male {idx + 1}"}
        for camp in camps:
            members = male_by_camp.get(camp, [])
            row[camp] = members[idx] if idx < len(members) else ""
        rows.append(row)

    return pd.DataFrame(rows, columns=["Slot"] + camps)


def run_camper_assignment(input_file_bytes: bytes, filename: str, config: dict, mapping: dict):
    file_type, tables = read_tables_from_upload(input_file_bytes, filename)
    cfg = apply_camper_mapping_to_config(config, mapping or {})
    if file_type == "csv":
        campers_df = tables["csv"]
    else:
        sheet = cfg["campers_sheet"]
        if sheet not in tables:
            raise ValueError(f"Camper sheet '{sheet}' not found in workbook.")
        campers_df = tables[sheet]
    required = [
        ("First Name", cfg["campers"]["first_name"]),
        ("Last Name", cfg["campers"]["last_name"]),
        ("Gender", cfg["campers"]["gender"]),
        ("Grade", cfg["campers"]["grade"]),
    ]
    missing_required = [label for label, col in required if not str(col).strip()]
    if missing_required:
        raise ValueError(
            "These camper fields are required and cannot be 'Not mapped': "
            + ", ".join(missing_required)
        )
    missing_columns = [label for label, col in required if col not in campers_df.columns]
    if missing_columns:
        raise ValueError(
            "Mapped required camper columns were not found in your file: "
            + ", ".join(missing_columns)
        )
    parsed_rows = parse_camper_rows(campers_df, cfg)
    if len(parsed_rows) == 0:
        raise ValueError(
            "No valid camper rows were parsed. Check your mapping for First Name, Last Name, "
            "Gender, Grade, and make sure Grade values are numeric."
        )

    camper_pack, camper_warnings = assign_campers(campers_df, cfg)
    cabin_assignments_df, cabin_summary_df, camper_audit_df = camper_pack
    warnings_df = (
        camper_warnings
        if not camper_warnings.empty
        else pd.DataFrame(columns=["level", "type", "message"])
    )

    metrics = [
        {"Metric": "Total cabin assignment rows", "Value": len(cabin_assignments_df)},
        {
            "Metric": "Open cabins",
            "Value": int((cabin_summary_df["Open Cabin"] == "Yes").sum())
            if not cabin_summary_df.empty
            else 0,
        },
        {"Metric": "Warnings", "Value": len(warnings_df)},
    ]
    metrics_df = pd.DataFrame(metrics)

    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
        cabin_assignments_df.to_excel(writer, index=False, sheet_name="cabin_assignments")
        cabin_summary_df.to_excel(writer, index=False, sheet_name="cabin_summary")
        camper_audit_df.to_excel(writer, index=False, sheet_name="camper_audit")
        warnings_df.to_excel(writer, index=False, sheet_name="warnings")
        metrics_df.to_excel(writer, index=False, sheet_name="metrics")
    output_bytes = output_buffer.getvalue()

    warning_rows = (
        warnings_df.fillna("").to_dict(orient="records") if not warnings_df.empty else []
    )
    unassigned_entries = []
    if not warnings_df.empty and {"type", "message"}.issubset(set(warnings_df.columns)):
        for _, row in warnings_df.iterrows():
            if str(row.get("type", "")).strip() != "unassigned-camper":
                continue
            structured_name = str(row.get("camper_name", "")).strip()
            if structured_name:
                detail = row.get("roommate_status_detail", [])
                if isinstance(detail, str):
                    try:
                        detail = json.loads(detail)
                    except Exception:
                        detail = []
                if not isinstance(detail, list):
                    detail = []
                unassigned_entries.append(
                    {
                        "week": str(row.get("week", "")).strip(),
                        "camper_id": str(row.get("camper_id", "")).strip(),
                        "name": structured_name,
                        "gender": str(row.get("gender", "")).strip(),
                        "reason": str(row.get("reason", "")).strip(),
                        "grade": str(row.get("grade", "")).strip(),
                        "disability_flag": str(row.get("disability_flag", "")).strip(),
                        "roommate_status_emojis": str(row.get("roommate_status_emojis", "")).strip(),
                        "roommate_status_detail": detail,
                    }
                )
                continue
            msg = str(row.get("message", "")).strip()
            # Expected format: "WeekX: First Last could not be assigned."
            parts = msg.split(":", 1)
            right = parts[1].strip() if len(parts) > 1 else msg
            name_part, reason_part = right, ""
            grade_part = ""
            disability_part = ""
            if "Reason:" in right:
                split = right.split("Reason:", 1)
                name_part = split[0].strip()
                reason_part = split[1].strip().rstrip(".")
            grade_match = re.search(r"Grade:\s*([^.]+)(?:\.|$)", name_part)
            if grade_match:
                grade_part = grade_match.group(1).strip()
            disability_match = re.search(r"Disability:\s*([^.]+)(?:\.|$)", name_part)
            if disability_match:
                disability_part = disability_match.group(1).strip()
            name_part = re.sub(r"Grade:\s*[^.]+(?:\.|$)", "", name_part).strip()
            name_part = re.sub(r"Disability:\s*[^.]+(?:\.|$)", "", name_part).strip()
            name_part = name_part.replace("could not be assigned.", "").strip()
            if name_part:
                unassigned_entries.append(
                    {
                        "name": name_part,
                        "reason": reason_part,
                        "grade": grade_part,
                        "disability_flag": disability_part,
                    }
                )

    cabin_layout_rows = (
        cabin_assignments_df[
            [
                "Week",
                "Cabin",
                "Cabin Gender",
                "Camper ID",
                "Camper Name",
                "Gender",
                "Grade",
                "School (normalized)",
                "Disability Flag",
                "Disability Raw",
                "Roommate Status Emojis",
                "Roommate Status Detail",
            ]
        ]
        .fillna("")
        .to_dict(orient="records")
        if not cabin_assignments_df.empty
        else []
    )
    return output_bytes, warning_rows, metrics, cabin_layout_rows, unassigned_entries


def run_counselor_assignment(
    input_file_bytes: bytes,
    filename: str,
    config: dict,
    mapping: dict,
    camp_parameters_text: str = "",
    single_camp_only: bool = False,
):
    file_type, tables = read_tables_from_upload(input_file_bytes, filename)
    cfg = apply_counselor_mapping_to_config(config, mapping or {})
    ordered_parameter_camps = parse_camp_parameter_order(camp_parameters_text)
    if len(ordered_parameter_camps) == 0:
        raise ValueError(
            "Counselor assignment now requires Camp Sessions in the textbox. "
            "Add one camp/session per line, then run again."
        )
    has_fixed_camps = True
    if file_type == "csv":
        if not mapping:
            raise ValueError(
                "CSV for counselor side needs mapping for counselor columns."
            )
        sheet = "csv"
    else:
        sheet = cfg["counselors_sheet"]
        if sheet not in tables:
            raise ValueError(f"Counselor sheet '{sheet}' not found in workbook.")
    counselors_df = tables[sheet]
    if counselors_df.empty:
        raise ValueError(
            "No counselor rows were found in the selected counselor sheet."
        )
    target_source_df = pd.DataFrame()

    # Target field UI mapping is intentionally hidden on counselor side.
    # Resolve target columns automatically from the selected target sheet.
    target_cols = []
    mapped_target_fields = (mapping or {}).get("target_fields", {})
    camp_col = str(mapped_target_fields.get("camp", "")).strip()
    total_col = str(mapped_target_fields.get("target_total", "")).strip()
    female_col = str(mapped_target_fields.get("target_female", "")).strip()
    male_col = str(mapped_target_fields.get("target_male", "")).strip()

    def positive_total_count(col_name: str) -> int:
        if not col_name or col_name not in target_cols:
            return 0
        series = pd.to_numeric(target_source_df[col_name], errors="coerce").fillna(0)
        return int((series > 0).sum())

    def valid_target_row_count(camp_name: str, total_name: str) -> int:
        if not camp_name or camp_name not in target_cols or not total_name or total_name not in target_cols:
            return 0
        camp_series = target_source_df[camp_name].fillna("").astype(str).str.strip()
        total_series = pd.to_numeric(target_source_df[total_name], errors="coerce").fillna(0)
        return int(((camp_series != "") & (total_series > 0)).sum())

    def text_like_camp_count(camp_name: str, total_name: str) -> int:
        if not camp_name or camp_name not in target_cols or not total_name or total_name not in target_cols:
            return 0
        camp_series = target_source_df[camp_name].fillna("").astype(str).str.strip()
        total_series = pd.to_numeric(target_source_df[total_name], errors="coerce").fillna(0)
        has_letters = camp_series.str.contains(r"[A-Za-z]", regex=True)
        return int(((camp_series != "") & (total_series > 0) & has_letters).sum())

    normalized_parameter_camps = [
        canonical_session_name(camp_name) for camp_name in ordered_parameter_camps
    ]
    slot_cfg = cfg.get("counselor_assignment", {}).get("slots_per_camp", {})
    female_slots = int(slot_cfg.get("female", COUNSELOR_FIXED_FEMALE_SLOTS))
    male_slots = int(slot_cfg.get("male", COUNSELOR_FIXED_MALE_SLOTS))
    female_slots = max(0, female_slots)
    male_slots = max(0, male_slots)
    camp_targets_df = pd.DataFrame(
        [
            {
                "Camp": camp_name,
                "Target Total": female_slots + male_slots,
                "Target Female": female_slots,
                "Target Male": male_slots,
            }
            for camp_name in normalized_parameter_camps
        ]
    )
    if camp_targets_df.empty:
        raise ValueError(
            "No camp target rows were found in the selected target sheet."
        )
    camp_targets_df["Camp"] = camp_targets_df["Camp"].fillna("").astype(str).str.strip()
    camp_targets_df["Camp"] = camp_targets_df["Camp"].apply(
        lambda x: ""
        if _norm(x) in {"nan", "none", "null", "nat", "undefined"}
        or re.fullmatch(r"-?\d+(?:\.0+)?", str(x).strip())
        else str(x).strip()
    )
    camp_series = camp_targets_df["Camp"]
    total_series = pd.to_numeric(
        camp_targets_df["Target Total"], errors="coerce"
    ).fillna(0)
    if not ((camp_series != "") & (total_series > 0)).any():
        raise ValueError(
            "No valid camp target rows found. Add at least one row with Camp and "
            "Target Total greater than 0."
        )
    required_counselor = [
        ("First Name", cfg["counselors"]["first_name"]),
        ("Last Name", cfg["counselors"]["last_name"]),
        ("Gender", cfg["counselors"]["gender"]),
        ("Availability", cfg["counselors"]["availability"]),
    ]
    missing_required = [label for label, col in required_counselor if not str(col).strip()]
    if missing_required:
        raise ValueError(
            "These counselor fields are required and cannot be 'Not mapped': "
            + ", ".join(missing_required)
        )
    counselor_missing_cols = [
        label for label, col in required_counselor if col not in counselors_df.columns
    ]
    if counselor_missing_cols:
        raise ValueError(
            "Mapped required counselor columns were not found in your file: "
            + ", ".join(counselor_missing_cols)
        )

    # Build a camp catalog from optional user parameters and observed target camps,
    # then canonicalize counselor availability/preference text to improve matching.
    camp_catalog = parse_camp_parameters(camp_parameters_text)
    for camp in camp_targets_df["Camp"].fillna("").astype(str).str.strip().tolist():
        if not camp:
            continue
        matched = best_match_camp_name(camp, camp_catalog) if camp_catalog else camp
        canonical = str(matched or camp).strip()
        if not canonical:
            continue
        if canonical not in camp_catalog:
            camp_catalog[canonical] = [canonical]
        if camp not in camp_catalog[canonical]:
            camp_catalog[canonical].append(camp)

    camp_targets_df["Camp"] = camp_targets_df["Camp"].apply(
        lambda x: best_match_camp_name(str(x or ""), camp_catalog)
    )
    counselors_df = counselors_df.copy()
    availability_col = cfg["counselors"].get("availability", "")
    if availability_col in counselors_df.columns:
        counselors_df[availability_col] = counselors_df[availability_col].apply(
            lambda x: normalize_camp_list_text(str(x or ""), camp_catalog)
        )
    for pref_key in ["preference_1", "preference_2", "preference_3"]:
        pref_col = cfg["counselors"].get(pref_key, "")
        if pref_col in counselors_df.columns:
            counselors_df[pref_col] = counselors_df[pref_col].apply(
                lambda x: best_match_camp_name(str(x or ""), camp_catalog)
            )

    counselor_assignments_df, counselor_warnings_df = assign_counselors(
        counselors_df, camp_targets_df, cfg, single_camp_only=single_camp_only
    )
    warnings_df = (
        counselor_warnings_df
        if not counselor_warnings_df.empty
        else pd.DataFrame(columns=["level", "type", "message"])
    )
    metrics = [
        {"Metric": "Counselor assignments", "Value": len(counselor_assignments_df)},
        {"Metric": "Warnings", "Value": len(warnings_df)},
    ]
    metrics_df = pd.DataFrame(metrics)

    warning_rows = (
        warnings_df.fillna("").to_dict(orient="records") if not warnings_df.empty else []
    )
    assignment_records = (
        counselor_assignments_df.fillna("").to_dict(orient="records")
        if not counselor_assignments_df.empty
        else []
    )

    target_work = camp_targets_df.copy()
    for col in ["Target Total", "Target Female", "Target Male"]:
        if col not in target_work.columns:
            target_work[col] = 0
        target_work[col] = pd.to_numeric(target_work[col], errors="coerce").fillna(0).astype(int)
    target_work["Camp"] = target_work["Camp"].fillna("").astype(str).str.strip()
    target_work = target_work[target_work["Camp"] != ""]
    target_work = (
        target_work.groupby("Camp", as_index=False)[["Target Total", "Target Female", "Target Male"]]
        .sum()
    )

    if counselor_assignments_df.empty:
        assigned_summary = pd.DataFrame(
            columns=["Camp", "Assigned Total", "Assigned Female", "Assigned Male"]
        )
    else:
        assigned_summary = (
            counselor_assignments_df.assign(
                Camp=counselor_assignments_df["Camp"].fillna("").astype(str).str.strip(),
                IsFemale=(counselor_assignments_df["Gender"] == "Female").astype(int),
                IsMale=(counselor_assignments_df["Gender"] == "Male").astype(int),
            )
            .groupby("Camp", as_index=False)
            .agg(
                **{
                    "Assigned Total": ("Counselor ID", "count"),
                    "Assigned Female": ("IsFemale", "sum"),
                    "Assigned Male": ("IsMale", "sum"),
                }
            )
        )

    target_summary_df = target_work.merge(assigned_summary, on="Camp", how="outer").fillna(0)
    for canonical in camp_catalog.keys():
        camp_name = str(canonical).strip()
        if not camp_name:
            continue
        if camp_name in set(target_summary_df.get("Camp", pd.Series(dtype=str)).astype(str).tolist()):
            continue
        target_summary_df = pd.concat(
            [
                target_summary_df,
                pd.DataFrame(
                    [
                        {
                            "Camp": camp_name,
                            "Target Total": 0,
                            "Target Female": 0,
                            "Target Male": 0,
                            "Assigned Total": 0,
                            "Assigned Female": 0,
                            "Assigned Male": 0,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    for col in [
        "Target Total",
        "Target Female",
        "Target Male",
        "Assigned Total",
        "Assigned Female",
        "Assigned Male",
    ]:
        target_summary_df[col] = pd.to_numeric(target_summary_df[col], errors="coerce").fillna(0).astype(int)
    target_summary_df["Unfilled Total"] = (
        target_summary_df["Target Total"] - target_summary_df["Assigned Total"]
    )
    target_summary_df["Unfilled Female"] = (
        target_summary_df["Target Female"] - target_summary_df["Assigned Female"]
    )
    target_summary_df["Unfilled Male"] = (
        target_summary_df["Target Male"] - target_summary_df["Assigned Male"]
    )
    target_summary_records = target_summary_df.sort_values("Camp").to_dict(orient="records")

    counselor_work = counselors_df.copy().reset_index(drop=True)
    counselor_work["Counselor ID"] = [f"S{i+1}" for i in range(len(counselor_work))]
    counselor_work["Counselor Name"] = (
        counselor_work[cfg["counselors"]["first_name"]].fillna("").astype(str).str.strip()
        + " "
        + counselor_work[cfg["counselors"]["last_name"]].fillna("").astype(str).str.strip()
    ).str.strip()
    counselor_work["Gender"] = counselor_work[cfg["counselors"]["gender"]].fillna("").astype(str).str.strip()
    counselor_work["Email"] = counselor_work[cfg["counselors"]["email"]].fillna("").astype(str).str.strip()
    counselor_work["Availability"] = (
        counselor_work[cfg["counselors"]["availability"]].fillna("").astype(str).str.strip()
    )
    assigned_ids = set(counselor_assignments_df.get("Counselor ID", pd.Series(dtype=str)).astype(str).tolist())
    camp_names_for_eligibility = [
        str(x).strip() for x in target_summary_df["Camp"].fillna("").astype(str).tolist() if str(x).strip()
    ]
    open_total_by_camp = {
        str(row["Camp"]).strip(): int(max(0, int(row["Unfilled Total"])))
        for _, row in target_summary_df.iterrows()
    }
    open_female_by_camp = {
        str(row["Camp"]).strip(): int(max(0, int(row["Unfilled Female"])))
        for _, row in target_summary_df.iterrows()
    }
    open_male_by_camp = {
        str(row["Camp"]).strip(): int(max(0, int(row["Unfilled Male"])))
        for _, row in target_summary_df.iterrows()
    }
    assigned_count_by_id = (
        counselor_assignments_df["Counselor ID"].astype(str).value_counts().to_dict()
        if not counselor_assignments_df.empty and "Counselor ID" in counselor_assignments_df.columns
        else {}
    )
    willing_col = cfg["counselors"].get("willing_camps", "")
    m = cfg["counselors"]

    def norm_gender_local(value: str) -> str:
        t = str(value or "").strip().lower()
        if t.startswith("f"):
            return "Female"
        if t.startswith("m"):
            return "Male"
        return "Unknown"

    def counselor_eligible_camps(row: pd.Series) -> List[str]:
        avail_raw = str(row.get("Availability", "") or "")
        avail_tokens = split_availability_list(avail_raw)
        out = []
        for camp in camp_names_for_eligibility:
            avail_ok = is_available_for_camp(camp, avail_tokens, avail_raw)
            pref_ok = preference_rank(camp, row, m) != "none"
            if avail_ok or pref_ok:
                out.append(camp)
        return out

    eligibility_summary = []
    for camp in camp_names_for_eligibility:
        total = 0
        female = 0
        male = 0
        for _, row in counselor_work.iterrows():
            eligible = camp in counselor_eligible_camps(row)
            if not eligible:
                continue
            total += 1
            g = norm_gender_local(row.get("Gender", ""))
            if g == "Female":
                female += 1
            elif g == "Male":
                male += 1
        eligibility_summary.append(
            {
                "camp": camp,
                "eligible_total": total,
                "eligible_female": female,
                "eligible_male": male,
            }
        )

    unassigned_counselors = []
    unassigned_df = counselor_work[~counselor_work["Counselor ID"].isin(assigned_ids)]
    for _, row in unassigned_df.iterrows():
        cid = str(row.get("Counselor ID", "")).strip()
        cname = str(row.get("Counselor Name", "")).strip()
        gender = str(row.get("Gender", "")).strip()
        email = str(row.get("Email", "")).strip()
        availability = str(row.get("Availability", "")).strip()
        eligible_camps = counselor_eligible_camps(row)
        g_norm = norm_gender_local(gender)
        assigned_count = int(assigned_count_by_id.get(cid, 0))
        max_capacity = (
            parse_capacity(row.get(willing_col, ""))
            if willing_col and willing_col in counselor_work.columns
            else 999
        )
        reason = ""
        if assigned_count >= (max_capacity + 2):
            reason = "Reached willing-camps limit (+2 soft cap)."
        elif not eligible_camps:
            reason = "No camps matched from availability/preferences."
        else:
            if g_norm == "Female":
                open_gender_camps = [c for c in eligible_camps if open_female_by_camp.get(c, 0) > 0]
            elif g_norm == "Male":
                open_gender_camps = [c for c in eligible_camps if open_male_by_camp.get(c, 0) > 0]
            else:
                open_gender_camps = [c for c in eligible_camps if open_total_by_camp.get(c, 0) > 0]
            if not open_gender_camps:
                reason = f"No open {g_norm.lower()} slots in eligible camps." if g_norm in {"Female", "Male"} else "No open slots in eligible camps."
            else:
                reason = "Lower score than other eligible counselors for remaining slots."
        unassigned_counselors.append(
            {
                "Counselor ID": cid,
                "Counselor Name": cname,
                "Gender": gender,
                "Email": email,
                "Availability": availability,
                "Reason": reason,
            }
        )

    warning_summary = {}
    for row in warning_rows:
        if str(row.get("type", "")).strip() != "unfilled-camp-slot":
            continue
        camp = str(row.get("camp", "")).strip()
        slot_need = str(row.get("slot_gender_need", "")).strip() or "Any"
        try:
            unfilled_count = max(1, int(float(str(row.get("unfilled_count", 1)).strip())))
        except Exception:
            unfilled_count = 1
        key = camp or "Unknown Camp"
        if key not in warning_summary:
            warning_summary[key] = {"camp": key, "unfilled_total": 0, "unfilled_female": 0, "unfilled_male": 0}
        warning_summary[key]["unfilled_total"] += unfilled_count
        if slot_need == "Female":
            warning_summary[key]["unfilled_female"] += unfilled_count
        elif slot_need == "Male":
            warning_summary[key]["unfilled_male"] += unfilled_count
    warning_summary_records = sorted(warning_summary.values(), key=lambda x: x["camp"])

    counselor_load_summary = []
    for _, row in counselor_work.iterrows():
        cid = str(row.get("Counselor ID", "")).strip()
        cname = str(row.get("Counselor Name", "")).strip() or "Unknown"
        willing_raw = str(row.get(willing_col, "")).strip() if willing_col else ""
        willing_cap = parse_capacity(willing_raw)
        assigned_count = int(assigned_count_by_id.get(cid, 0))
        willing_norm = willing_raw.lower()
        if not willing_norm:
            status_emoji = "👌🏼"
            status_reason = "No willing-camps value provided."
        elif "as many" in willing_norm or willing_norm in {"all", "any", "unlimited", "no limit"}:
            if assigned_count == 0:
                status_emoji = "🥶"
                status_reason = "Unlimited willingness but currently assigned to zero camps."
            else:
                status_emoji = "👌🏼"
                status_reason = "Unlimited willingness value."
        else:
            if assigned_count > willing_cap:
                status_emoji = "🥵"
                status_reason = "Assigned to more camps than willing-camps value."
            elif assigned_count == willing_cap:
                status_emoji = "👌🏼"
                status_reason = "Assigned to exactly willing-camps value."
            else:
                status_emoji = "🥶"
                status_reason = "Assigned to fewer camps than willing-camps value."
        counselor_load_summary.append(
            {
                "counselor_id": cid,
                "counselor_name": cname,
                "gender": str(row.get("Gender", "")).strip(),
                "assigned_count": assigned_count,
                "willing_raw": willing_raw,
                "willing_capacity": willing_cap,
                "status_emoji": status_emoji,
                "status_reason": status_reason,
            }
        )
    counselor_load_summary = sorted(counselor_load_summary, key=lambda x: x["counselor_name"].lower())

    fixed_camp_order = []
    seen_fixed = set()
    for raw_name in normalized_parameter_camps:
        canonical = canonical_session_name(str(raw_name or "").strip())
        key = _norm(canonical)
        if not canonical or key in seen_fixed:
            continue
        seen_fixed.add(key)
        fixed_camp_order.append(canonical)

    counselor_layout_df = build_counselor_layout_df(
        counselor_assignments_df, camp_targets_df, fixed_camp_order
    )

    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
        counselor_layout_df.to_excel(writer, index=False, sheet_name="counselor_layout")
        counselor_assignments_df.to_excel(
            writer, index=False, sheet_name="counselor_assignments"
        )
        warnings_df.to_excel(writer, index=False, sheet_name="warnings")
        metrics_df.to_excel(writer, index=False, sheet_name="metrics")
    output_bytes = output_buffer.getvalue()

    review_payload = {
        "assignments": assignment_records,
        "target_summary": target_summary_records,
        "unassigned_counselors": unassigned_counselors,
        "eligibility_summary": eligibility_summary,
        "warning_summary": warning_summary_records,
        "counselor_load_summary": counselor_load_summary,
        "camp_catalog": fixed_camp_order,
        "fixed_camp_order": fixed_camp_order,
    }
    return output_bytes, warning_rows, metrics, review_payload


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/default-settings")
def api_default_settings():
    cfg = load_default_config()
    payload = {
        "max_roommate_requests_per_camper": cfg.get("max_roommate_requests_per_camper", 2),
        "cabins": {
            "total_per_week": cfg["cabins"].get("total_per_week", 7),
            "max_per_cabin": cfg["cabins"].get("max_per_cabin", 12),
            "min_per_open_cabin": cfg["cabins"].get("min_per_open_cabin", 7),
            "max_disability_per_cabin": cfg["cabins"].get("max_disability_per_cabin", 2),
            "max_same_school_per_cabin": cfg["cabins"].get("max_same_school_per_cabin", 4),
            "strict_grade_span": cfg["cabins"].get("strict_grade_span", 2),
            "strict_adjacent_grades": cfg["cabins"].get("strict_adjacent_grades", True),
        },
        "matching": {
            "name_fuzzy_threshold": cfg["matching"].get("name_fuzzy_threshold", 82),
            "school_fuzzy_threshold": cfg["matching"].get("school_fuzzy_threshold", 90),
        },
        "counselor_assignment": {
            "friend_bonus": cfg["counselor_assignment"].get("friend_bonus", 8),
            "slots_per_camp": {
                "female": cfg["counselor_assignment"].get("slots_per_camp", {}).get("female", 12),
                "male": cfg["counselor_assignment"].get("slots_per_camp", {}).get("male", 9),
            },
            "preference_scores": {
                "1": cfg["counselor_assignment"]["preference_scores"].get("1", 100),
                "2": cfg["counselor_assignment"]["preference_scores"].get("2", 70),
                "3": cfg["counselor_assignment"]["preference_scores"].get("3", 40),
            },
        },
    }
    return jsonify({"ok": True, "settings": payload})


@app.get("/api/template/campers")
def download_camper_template():
    config = load_default_config()
    data = build_template_workbook_bytes(
        config, include_campers=True, include_counselors=False, include_targets=False
    )
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="camper_input_template.xlsx",
    )


@app.get("/api/template/counselors")
def download_counselor_template():
    config = load_default_config()
    data = build_template_workbook_bytes(
        config, include_campers=False, include_counselors=True, include_targets=True
    )
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="counselor_input_template.xlsx",
    )


@app.post("/api/inspect/campers")
def api_inspect_campers():
    if "input_file" not in request.files:
        return jsonify({"ok": False, "error": "Please upload a file first."}), 400
    input_file = request.files["input_file"]
    if input_file.filename == "":
        return jsonify({"ok": False, "error": "Please select a file."}), 400
    config_file = request.files.get("config_file")
    try:
        config = parse_config(config_file)
        file_type, tables = read_tables_from_upload(input_file.read(), input_file.filename)
        payload = build_camper_mapping_suggestions(config, file_type, tables)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "mapping": payload})


@app.post("/api/inspect/counselors")
def api_inspect_counselors():
    if "input_file" not in request.files:
        return jsonify({"ok": False, "error": "Please upload a file first."}), 400
    input_file = request.files["input_file"]
    if input_file.filename == "":
        return jsonify({"ok": False, "error": "Please select a file."}), 400
    config_file = request.files.get("config_file")
    try:
        config = parse_config(config_file)
        file_type, tables = read_tables_from_upload(input_file.read(), input_file.filename)
        payload = build_counselor_mapping_suggestions(config, file_type, tables)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "mapping": payload})


@app.post("/api/run/campers")
def api_run_campers():
    if "input_file" not in request.files:
        return jsonify({"ok": False, "error": "Please upload an input workbook first."}), 400

    input_file = request.files["input_file"]
    if input_file.filename == "":
        return jsonify({"ok": False, "error": "Please select an input workbook file."}), 400

    config_file = request.files.get("config_file")
    mapping_json = request.form.get("mapping_json", "")
    settings_overrides_json = request.form.get("settings_overrides_json", "")
    try:
        config = parse_config(config_file)
        settings_overrides = (
            json.loads(settings_overrides_json) if settings_overrides_json else {}
        )
        config = deep_merge_dict(config, settings_overrides)
        mapping = json.loads(mapping_json) if mapping_json else {}
        output_bytes, warnings, metrics, cabin_layout, unassigned_names = run_camper_assignment(
            input_file.read(), input_file.filename, config, mapping
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    run_id = str(uuid.uuid4())
    RESULTS[run_id] = output_bytes
    return jsonify(
        {
            "ok": True,
            "run_id": run_id,
            "warnings": warnings,
            "metrics": metrics,
            "cabin_layout": cabin_layout,
            "unassigned_names": unassigned_names,
        }
    )


@app.post("/api/run/counselors")
def api_run_counselors():
    if "input_file" not in request.files:
        return jsonify({"ok": False, "error": "Please upload an input workbook first."}), 400

    input_file = request.files["input_file"]
    if input_file.filename == "":
        return jsonify({"ok": False, "error": "Please select an input workbook file."}), 400

    config_file = request.files.get("config_file")
    mapping_json = request.form.get("mapping_json", "")
    settings_overrides_json = request.form.get("settings_overrides_json", "")
    camp_parameters_text = request.form.get("camp_parameters_text", "")
    single_camp_only = str(request.form.get("single_camp_only", "false")).strip().lower() in {"1", "true", "yes", "on"}
    try:
        config = parse_config(config_file)
        settings_overrides = (
            json.loads(settings_overrides_json) if settings_overrides_json else {}
        )
        config = deep_merge_dict(config, settings_overrides)
        mapping = json.loads(mapping_json) if mapping_json else {}
        output_bytes, warnings, metrics, review_payload = run_counselor_assignment(
            input_file.read(),
            input_file.filename,
            config,
            mapping,
            camp_parameters_text=camp_parameters_text,
            single_camp_only=single_camp_only,
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    run_id = str(uuid.uuid4())
    RESULTS[run_id] = output_bytes
    return jsonify(
        {
            "ok": True,
            "run_id": run_id,
            "warnings": warnings,
            "metrics": metrics,
            "review": review_payload,
        }
    )


@app.get("/api/download/<run_id>")
def api_download(run_id):
    data = RESULTS.get(run_id)
    if data is None:
        return jsonify({"ok": False, "error": "Run not found. Please run assignment again."}), 404
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="output_assignments.xlsx",
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
