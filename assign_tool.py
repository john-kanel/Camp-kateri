#!/usr/bin/env python3
import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz, process


TRUTHY = {"1", "true", "yes", "y", "x", "checked"}
DISABILITY_NO_VALUES = {"n/a", "none", "no", "na", "", "nan", "null", "nat"}
NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
}


@dataclass
class Camper:
    camper_id: str
    week: str
    first_name: str
    last_name: str
    full_name: str
    gender: str
    grade: int
    school_raw: str
    school: str
    disability: bool
    disability_raw: str
    roommate_text: str
    roommate_tokens: List[str] = field(default_factory=list)
    roommate_ids: List[str] = field(default_factory=list)
    roommate_resolution: List[dict] = field(default_factory=list)
    component_id: str = ""


@dataclass
class Cabin:
    week: str
    cabin_id: str
    gender: str
    is_open: bool
    members: List[str] = field(default_factory=list)
    disability_count: int = 0
    school_counts: Counter = field(default_factory=Counter)
    component_counts: Counter = field(default_factory=Counter)
    min_grade: Optional[int] = None
    max_grade: Optional[int] = None


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def parse_args():
    parser = argparse.ArgumentParser(
        description="Assign campers to cabins and counselors to camps."
    )
    parser.add_argument("--input", help="Input Excel file path")
    parser.add_argument("--output", help="Output Excel file path")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Config JSON file path (default: config.json)",
    )
    parser.add_argument(
        "--init-workbook",
        help="Create a starter workbook (Step 1) at this path and exit",
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_gender(value: str) -> str:
    v = normalize_text(value)
    if v.startswith("f") or v.startswith("g") or "girl" in v or "woman" in v:
        return "Female"
    if v.startswith("m") or v.startswith("b") or "boy" in v or "man" in v:
        return "Male"
    return "Unknown"


def to_bool(value) -> bool:
    return normalize_text(value) in TRUTHY


def disability_flag(value) -> bool:
    v = normalize_text(value)
    return v not in DISABILITY_NO_VALUES


def to_int(value, default: int = -1) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def parse_grade_value(value, default: int = -1) -> int:
    raw = normalize_text(value)
    if raw in {"", "nan", "none", "null", "nat"}:
        return default

    # Accept direct numeric forms (e.g., "6", "6.0").
    direct = to_int(raw, default=None)
    if direct is not None:
        return direct

    # Accept embedded numeric forms (e.g., "grade 6", "6th grade").
    m_num = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", raw)
    if m_num:
        return int(m_num.group(1))

    # Accept word forms (e.g., "grade six", "sixth grade").
    m_word = re.search(
        r"\b("
        r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth"
        r")\b",
        raw,
    )
    if m_word:
        token = m_word.group(1)
        if token in NUMBER_WORDS:
            return NUMBER_WORDS[token]
        if token in ORDINAL_WORDS:
            return ORDINAL_WORDS[token]

    return default


def split_tokens(text: str, regex: str, max_items: int) -> List[str]:
    if not text or normalize_text(text) in {"", "nan", "none"}:
        return []
    raw = normalize_text(text)
    # Convert numbered-list styles into separators:
    # "1.name -2. other" -> ", name , other"
    raw = re.sub(r"(^|\s)\d+\s*[\.\)\-:]\s*", ", ", raw)
    raw = re.sub(r"\s*-\s*(?=\d+\s*[\.\)\-:])", ", ", raw)
    # Normalize common separators used in manual entry.
    raw = re.sub(r"\s+(and|&)\s+", ",", raw, flags=re.IGNORECASE)
    raw = raw.replace(";", ",").replace("/", ",")
    # Treat period followed by space as a likely separator between names:
    # "john kanel. harry potter"
    raw = re.sub(r"\.\s+(?=[a-z])", ", ", raw)
    parts = [normalize_text(x) for x in raw.split(",")]
    cleaned = []
    for p in parts:
        p = re.sub(r"^\d+\s*[\.\)\-:]\s*", "", p)
        p = re.sub(r"[^a-z0-9\s\-']", " ", p).strip()
        p = re.sub(r"\s+", " ", p)
        if p:
            cleaned.append(p)
    parts = cleaned
    # Keep unique token order and cap at configured limit.
    seen = set()
    tokens = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        tokens.append(p)
    return tokens[:max_items]


def canonicalize_schools(values: List[str], threshold: int, other_labels: List[str]) -> Dict[str, str]:
    canonical_map: Dict[str, str] = {}
    canonicals: List[str] = []
    other_set = {normalize_text(x) for x in other_labels}
    for raw in values:
        key = normalize_text(raw)
        if key in other_set:
            canonical_map[key] = "__OTHER__"
            continue
        if not key:
            canonical_map[key] = "__OTHER__"
            continue
        if not canonicals:
            canonicals.append(key)
            canonical_map[key] = key
            continue
        match = process.extractOne(key, canonicals, scorer=fuzz.ratio)
        if match and match[1] >= threshold:
            canonical_map[key] = match[0]
        else:
            canonicals.append(key)
            canonical_map[key] = key
    return canonical_map


def choose_gender_split(total_cabins: int, females: int, males: int, max_per_cabin: int) -> Tuple[int, int]:
    min_f = math.ceil(females / max_per_cabin) if females > 0 else 0
    min_m = math.ceil(males / max_per_cabin) if males > 0 else 0
    min_f = min(min_f, total_cabins)
    min_m = min(min_m, total_cabins)
    best = None
    total = females + males
    for f in range(min_f, total_cabins - min_m + 1):
        m = total_cabins - f
        if f < min_f or m < min_m:
            continue
        ratio = (f / total_cabins) if total_cabins else 0
        target = (females / total) if total else 0.5
        score = abs(ratio - target)
        if best is None or score < best[0]:
            best = (score, f, m)
    if best is None:
        return total_cabins // 2, total_cabins - (total_cabins // 2)
    return best[1], best[2]


def choose_open_cabins(count: int, designated: int, min_per_cabin: int, max_per_cabin: int) -> int:
    if count == 0 or designated == 0:
        return 0
    min_open = math.ceil(count / max_per_cabin)
    max_open = count // min_per_cabin
    if max_open <= 0:
        return 1
    open_cabins = min(designated, max(min_open, min(max_open, round(count / 10) or 1)))
    return max(1, open_cabins)


def build_cabins_for_week(
    week: str,
    total_cabins: int,
    female_count: int,
    male_count: int,
    min_per_cabin: int,
    max_per_cabin: int,
) -> List[Cabin]:
    female_designated, male_designated = choose_gender_split(
        total_cabins, female_count, male_count, max_per_cabin
    )
    female_open = choose_open_cabins(
        female_count, female_designated, min_per_cabin, max_per_cabin
    )
    male_open = choose_open_cabins(male_count, male_designated, min_per_cabin, max_per_cabin)

    cabins = []
    idx = 1
    for i in range(female_designated):
        cabins.append(
            Cabin(
                week=week,
                cabin_id=f"Cabin {idx}",
                gender="Female",
                is_open=i < female_open,
            )
        )
        idx += 1
    for i in range(male_designated):
        cabins.append(
            Cabin(
                week=week,
                cabin_id=f"Cabin {idx}",
                gender="Male",
                is_open=i < male_open,
            )
        )
        idx += 1
    while len(cabins) < total_cabins:
        cabins.append(Cabin(week=week, cabin_id=f"Cabin {idx}", gender="Unassigned", is_open=False))
        idx += 1
    return cabins


def can_place(
    camper: Camper,
    cabin: Cabin,
    campers_by_id: Dict[str, Camper],
    max_size: int,
    max_disability: int,
    max_same_school: int,
    strict_adjacent_grades: bool,
    strict_grade_span: int,
) -> bool:
    if not cabin.is_open:
        return False
    if cabin.gender != camper.gender:
        return False
    if len(cabin.members) >= max_size:
        return False
    if camper.disability and cabin.disability_count >= max_disability:
        return False
    if camper.school != "__OTHER__" and cabin.school_counts[camper.school] >= max_same_school:
        return False
    if strict_adjacent_grades:
        if cabin.min_grade is not None:
            new_min = min(cabin.min_grade, camper.grade)
            new_max = max(cabin.max_grade, camper.grade)
            if (new_max - new_min) > strict_grade_span:
                return False
    return True


def place_camper(camper: Camper, cabin: Cabin):
    cabin.members.append(camper.camper_id)
    if camper.disability:
        cabin.disability_count += 1
    if camper.school != "__OTHER__":
        cabin.school_counts[camper.school] += 1
    if camper.component_id:
        cabin.component_counts[camper.component_id] += 1
    if cabin.min_grade is None:
        cabin.min_grade = camper.grade
        cabin.max_grade = camper.grade
    else:
        cabin.min_grade = min(cabin.min_grade, camper.grade)
        cabin.max_grade = max(cabin.max_grade, camper.grade)


def rebuild_cabin_state(cabin: Cabin, campers_by_id: Dict[str, Camper]):
    cabin.disability_count = 0
    cabin.school_counts = Counter()
    cabin.component_counts = Counter()
    cabin.min_grade = None
    cabin.max_grade = None
    members = list(cabin.members)
    cabin.members = []
    for mid in members:
        place_camper(campers_by_id[mid], cabin)


def roommate_fulfilled_count(camper: Camper, cabin: Cabin) -> int:
    if not camper.roommate_ids:
        return 0
    cabin_set = set(cabin.members)
    return sum(1 for rid in camper.roommate_ids if rid in cabin_set)


def build_camper_to_cabin(cabins: List[Cabin]) -> Dict[str, Cabin]:
    out = {}
    for cabin in cabins:
        for mid in cabin.members:
            out[mid] = cabin
    return out


def build_requested_by(campers_by_id: Dict[str, Camper]) -> Dict[str, set]:
    requested_by = defaultdict(set)
    for requester_id, camper in campers_by_id.items():
        for rid in camper.roommate_ids:
            requested_by[rid].add(requester_id)
    return requested_by


def camper_roommate_score(camper: Camper, cabin: Cabin, campers_by_id: Dict[str, Camper]) -> int:
    if not camper.roommate_ids:
        return 0
    cabin_set = set(cabin.members)
    fulfilled = 0
    mutual_fulfilled = 0
    for rid in camper.roommate_ids:
        if rid not in cabin_set:
            continue
        fulfilled += 1
        other = campers_by_id.get(rid)
        if other and camper.camper_id in set(other.roommate_ids):
            mutual_fulfilled += 1
    any_fulfilled = 1 if fulfilled > 0 else 0
    # Lexicographic-like weighting:
    # 1) maximize campers with >=1 fulfilled request
    # 2) maximize total fulfilled requests
    # 3) prefer mutual roommate matches when possible
    return (any_fulfilled * 120) + (fulfilled * 40) + (mutual_fulfilled * 15)


def impacted_campers_for_move(
    mover_id: str,
    source: Cabin,
    target: Cabin,
    campers_by_id: Dict[str, Camper],
    requested_by: Dict[str, set],
) -> set:
    impacted = {mover_id}
    impacted.update(source.members)
    impacted.update(target.members)
    mover = campers_by_id[mover_id]
    impacted.update(mover.roommate_ids)
    impacted.update(requested_by.get(mover_id, set()))
    for mid in list(source.members) + list(target.members):
        camper = campers_by_id[mid]
        impacted.update(camper.roommate_ids)
        impacted.update(requested_by.get(mid, set()))
    return impacted


def score_impacted(
    impacted_ids: set,
    camper_to_cabin: Dict[str, Cabin],
    campers_by_id: Dict[str, Camper],
) -> int:
    total = 0
    for cid in impacted_ids:
        camper = campers_by_id.get(cid)
        cabin = camper_to_cabin.get(cid)
        if not camper or not cabin:
            continue
        total += camper_roommate_score(camper, cabin, campers_by_id)
    return total


def improve_roommate_fulfillment(
    cabins: List[Cabin],
    campers_by_id: Dict[str, Camper],
    config: dict,
    enforce_grade_rules: bool,
    max_passes: int = 8,
):
    max_size = config["cabins"]["max_per_cabin"]
    max_disability = config["cabins"]["max_disability_per_cabin"]
    max_same_school = config["cabins"]["max_same_school_per_cabin"]
    min_per_open = config["cabins"]["min_per_open_cabin"]
    strict_grade_span = int(config["cabins"].get("strict_grade_span", 2))
    all_requesting = [c for c in campers_by_id.values() if len(c.roommate_ids) > 0]
    if not all_requesting:
        return
    requested_by = build_requested_by(campers_by_id)

    for _ in range(max_passes):
        camper_to_cabin = build_camper_to_cabin(cabins)
        candidates = [c for c in all_requesting if c.camper_id in camper_to_cabin]
        candidates.sort(
            key=lambda c: (
                roommate_fulfilled_count(c, camper_to_cabin[c.camper_id]),
                -len(c.roommate_ids),
                c.last_name,
            )
        )

        best_action = None
        best_gain = 0

        for camper in candidates:
            current_cabin = camper_to_cabin.get(camper.camper_id)
            if not current_cabin:
                continue

            candidate_targets = []
            for rid in camper.roommate_ids:
                rc = camper_to_cabin.get(rid)
                if rc and rc != current_cabin and rc.gender == camper.gender:
                    candidate_targets.append(rc)
            if not candidate_targets:
                candidate_targets = [c for c in cabins if c != current_cabin and c.gender == camper.gender and c.is_open]

            seen_targets = set()
            dedup_targets = []
            for tc in candidate_targets:
                k = (tc.week, tc.cabin_id)
                if k in seen_targets:
                    continue
                seen_targets.add(k)
                dedup_targets.append(tc)

            for target_cabin in dedup_targets:
                if target_cabin.week != current_cabin.week:
                    continue
                # Keep source cabin either empty or at/above minimum open size.
                if len(current_cabin.members) - 1 not in {0} and (len(current_cabin.members) - 1) < min_per_open:
                    continue

                impacted = impacted_campers_for_move(
                    camper.camper_id, current_cabin, target_cabin, campers_by_id, requested_by
                )
                before_score = score_impacted(impacted, camper_to_cabin, campers_by_id)

                # Direct move test.
                if camper.camper_id in current_cabin.members:
                    current_cabin.members.remove(camper.camper_id)
                    rebuild_cabin_state(current_cabin, campers_by_id)
                    can_direct = can_place(
                        camper,
                        target_cabin,
                        campers_by_id,
                        max_size,
                        max_disability,
                        max_same_school,
                        enforce_grade_rules,
                        strict_grade_span,
                    )
                    if can_direct:
                        place_camper(camper, target_cabin)
                        after_map = build_camper_to_cabin(cabins)
                        after_score = score_impacted(impacted, after_map, campers_by_id)
                        gain = after_score - before_score
                        if gain > best_gain:
                            best_gain = gain
                            best_action = ("move", camper.camper_id, None, current_cabin, target_cabin)
                        target_cabin.members.remove(camper.camper_id)
                        rebuild_cabin_state(target_cabin, campers_by_id)
                    place_camper(camper, current_cabin)

                # Swap test.
                for swap_id in list(target_cabin.members):
                    if swap_id == camper.camper_id:
                        continue
                    swapper = campers_by_id[swap_id]
                    if swapper.gender != camper.gender:
                        continue

                    if camper.camper_id not in current_cabin.members or swap_id not in target_cabin.members:
                        continue
                    current_cabin.members.remove(camper.camper_id)
                    target_cabin.members.remove(swap_id)
                    rebuild_cabin_state(current_cabin, campers_by_id)
                    rebuild_cabin_state(target_cabin, campers_by_id)

                    can_put_camper = can_place(
                        camper,
                        target_cabin,
                        campers_by_id,
                        max_size,
                        max_disability,
                        max_same_school,
                        enforce_grade_rules,
                        strict_grade_span,
                    )
                    can_put_swapper = can_place(
                        swapper,
                        current_cabin,
                        campers_by_id,
                        max_size,
                        max_disability,
                        max_same_school,
                        enforce_grade_rules,
                        strict_grade_span,
                    )
                    if can_put_camper and can_put_swapper:
                        place_camper(camper, target_cabin)
                        place_camper(swapper, current_cabin)
                        after_map = build_camper_to_cabin(cabins)
                        after_score = score_impacted(impacted, after_map, campers_by_id)
                        gain = after_score - before_score
                        if gain > best_gain:
                            best_gain = gain
                            best_action = ("swap", camper.camper_id, swap_id, current_cabin, target_cabin)
                        target_cabin.members.remove(camper.camper_id)
                        current_cabin.members.remove(swap_id)
                        rebuild_cabin_state(target_cabin, campers_by_id)
                        rebuild_cabin_state(current_cabin, campers_by_id)

                    place_camper(camper, current_cabin)
                    place_camper(swapper, target_cabin)

        if not best_action or best_gain <= 0:
            break
        action, camper_id, swap_id, source_cabin, target_cabin = best_action
        mover = campers_by_id[camper_id]
        if action == "move":
            if camper_id in source_cabin.members:
                source_cabin.members.remove(camper_id)
                rebuild_cabin_state(source_cabin, campers_by_id)
                place_camper(mover, target_cabin)
        else:
            if camper_id in source_cabin.members and swap_id in target_cabin.members:
                swapper = campers_by_id[swap_id]
                source_cabin.members.remove(camper_id)
                target_cabin.members.remove(swap_id)
                rebuild_cabin_state(source_cabin, campers_by_id)
                rebuild_cabin_state(target_cabin, campers_by_id)
                place_camper(mover, target_cabin)
                place_camper(swapper, source_cabin)


def score_cabin(camper: Camper, cabin: Cabin, campers_by_id: Dict[str, Camper], target_size: float) -> float:
    score = 0.0
    # Keep cabin balance as a soft preference only.
    # Roommate outcomes should win when there is a tradeoff.
    score += abs((len(cabin.members) + 1) - target_size) * 0.35

    # Prefer matching roommate requests (mutual > one-way).
    roommates = set(camper.roommate_ids)
    for cid in cabin.members:
        if cid in roommates:
            other = campers_by_id[cid]
            if camper.camper_id in set(other.roommate_ids):
                score -= 18.0
            else:
                score -= 10.0

    # Split larger friendship components.
    if camper.component_id:
        score += cabin.component_counts[camper.component_id] * 3.8

    # Spread schools.
    if camper.school != "__OTHER__":
        score += cabin.school_counts[camper.school] * 2.2

    return score


def score_pair_in_cabin(
    camper_a: Camper,
    camper_b: Camper,
    cabin: Cabin,
    campers_by_id: Dict[str, Camper],
    target_size: float,
) -> float:
    # Approximate pair score by placing A then B.
    s1 = score_cabin(camper_a, cabin, campers_by_id, target_size)
    temp_members = list(cabin.members) + [camper_a.camper_id]
    # Temporary cabin-like values for roommate scoring effect.
    temp_score = 0.0
    temp_score += abs((len(temp_members) + 1) - target_size) * 0.35
    roommates = set(camper_b.roommate_ids)
    for cid in temp_members:
        if cid in roommates:
            other = campers_by_id[cid]
            if camper_b.camper_id in set(other.roommate_ids):
                temp_score -= 18.0
            else:
                temp_score -= 10.0
    if camper_b.component_id:
        temp_score += (cabin.component_counts[camper_b.component_id] + (1 if camper_a.component_id == camper_b.component_id else 0)) * 3.8
    if camper_b.school != "__OTHER__":
        temp_score += (cabin.school_counts[camper_b.school] + (1 if camper_a.school == camper_b.school else 0)) * 2.2
    return s1 + temp_score


def explain_unassigned_reason(
    camper: Camper,
    cabins: List[Cabin],
    config: dict,
    consider_grade_rule: bool,
) -> str:
    if camper.gender not in {"Female", "Male"}:
        return "missing or invalid gender value"
    open_gender_cabins = [c for c in cabins if c.is_open and c.gender == camper.gender]
    if not open_gender_cabins:
        return "no open cabin available for this gender"

    max_size = config["cabins"]["max_per_cabin"]
    max_disability = config["cabins"]["max_disability_per_cabin"]
    max_same_school = config["cabins"]["max_same_school_per_cabin"]
    strict_grade_span = int(config["cabins"].get("strict_grade_span", 2))
    strict_on = consider_grade_rule and config["cabins"]["strict_adjacent_grades"]

    all_full = all(len(c.members) >= max_size for c in open_gender_cabins)
    if all_full:
        return "all matching cabins are full"

    reasons = []
    if camper.disability and all(c.disability_count >= max_disability for c in open_gender_cabins):
        reasons.append("disability support cap reached in matching cabins")
    if camper.school != "__OTHER__":
        if all(c.school_counts[camper.school] >= max_same_school for c in open_gender_cabins):
            reasons.append("same-school limit reached in matching cabins")
    if strict_on:
        grade_blocked = True
        for c in open_gender_cabins:
            if len(c.members) >= max_size:
                continue
            if c.min_grade is None:
                grade_blocked = False
                break
            new_min = min(c.min_grade, camper.grade)
            new_max = max(c.max_grade, camper.grade)
            if (new_max - new_min) <= strict_grade_span:
                grade_blocked = False
                break
        if grade_blocked:
            reasons.append("grade span would exceed configured range")

    if reasons:
        return "; ".join(reasons)
    return "no cabin satisfies all hard constraints"


def assign_group(
    group: List[Camper],
    cabins: List[Cabin],
    campers_by_id: Dict[str, Camper],
    config: dict,
    warnings: List[dict],
    grade_strict: bool,
) -> List[Camper]:
    max_size = config["cabins"]["max_per_cabin"]
    max_disability = config["cabins"]["max_disability_per_cabin"]
    max_same_school = config["cabins"]["max_same_school_per_cabin"]
    strict_grade_span = int(config["cabins"].get("strict_grade_span", 2))
    target_size = len(group) / max(1, len([c for c in cabins if c.is_open]))

    group_sorted = sorted(
        group,
        key=lambda c: (
            0 if c.disability else 1,
            -len(c.roommate_ids),
            c.grade,
            c.last_name,
        ),
    )

    by_id_group = {c.camper_id: c for c in group}
    placed = set()

    # Pass 1: place strong mutual roommate pairs first.
    mutual_pairs = []
    for camper in group:
        for rid in camper.roommate_ids:
            if rid in by_id_group and camper.camper_id in set(by_id_group[rid].roommate_ids):
                pair = tuple(sorted([camper.camper_id, rid]))
                if pair not in mutual_pairs:
                    mutual_pairs.append(pair)
    mutual_pairs = sorted(
        mutual_pairs,
        key=lambda p: (
            -(len(by_id_group[p[0]].roommate_ids) + len(by_id_group[p[1]].roommate_ids)),
            by_id_group[p[0]].last_name,
        ),
    )

    for a_id, b_id in mutual_pairs:
        if a_id in placed or b_id in placed:
            continue
        a = by_id_group[a_id]
        b = by_id_group[b_id]
        valid_cabins = []
        for c in cabins:
            if not can_place(
                a,
                c,
                campers_by_id,
                max_size,
                max_disability,
                max_same_school,
                grade_strict and config["cabins"]["strict_adjacent_grades"],
                strict_grade_span,
            ):
                continue
            # Simulate A then verify B fits.
            place_camper(a, c)
            b_ok = can_place(
                b,
                c,
                campers_by_id,
                max_size,
                max_disability,
                max_same_school,
                grade_strict and config["cabins"]["strict_adjacent_grades"],
                strict_grade_span,
            )
            # Undo A simulation.
            c.members.remove(a.camper_id)
            c.disability_count = 0
            c.school_counts = Counter()
            c.component_counts = Counter()
            c.min_grade = None
            c.max_grade = None
            rebuilt = list(c.members)
            c.members = []
            for mid in rebuilt:
                place_camper(campers_by_id[mid], c)
            if b_ok:
                valid_cabins.append(c)
        if not valid_cabins:
            continue
        best_cabin = min(
            valid_cabins,
            key=lambda c: score_pair_in_cabin(a, b, c, campers_by_id, target_size),
        )
        place_camper(a, best_cabin)
        place_camper(b, best_cabin)
        placed.add(a_id)
        placed.add(b_id)

    unassigned = []
    for camper in group_sorted:
        if camper.camper_id in placed:
            continue
        valid = [
            c
            for c in cabins
            if can_place(
                camper,
                c,
                campers_by_id,
                max_size,
                max_disability,
                max_same_school,
                grade_strict and config["cabins"]["strict_adjacent_grades"],
                strict_grade_span,
            )
        ]
        if not valid:
            unassigned.append(camper)
            continue
        chosen = min(valid, key=lambda c: score_cabin(camper, c, campers_by_id, target_size))
        place_camper(camper, chosen)
    if unassigned and grade_strict:
        warnings.append(
            {
                "level": "warning",
                "type": "grade-strict-unassigned",
                "message": f"{len(unassigned)} campers could not be placed with strict adjacent-grade rules.",
            }
        )
    return unassigned


def rebalance_min_size(
    cabins: List[Cabin],
    campers_by_id: Dict[str, Camper],
    config: dict,
    warnings: List[dict],
):
    min_size = config["cabins"]["min_per_open_cabin"]
    max_size = config["cabins"]["max_per_cabin"]
    max_disability = config["cabins"]["max_disability_per_cabin"]
    max_same_school = config["cabins"]["max_same_school_per_cabin"]
    strict_grades = config["cabins"]["strict_adjacent_grades"]
    strict_grade_span = int(config["cabins"].get("strict_grade_span", 2))

    changed = True
    while changed:
        changed = False
        small = [c for c in cabins if c.is_open and 0 < len(c.members) < min_size]
        large = [c for c in cabins if c.is_open and len(c.members) > min_size]
        if not small or not large:
            break
        for target in small:
            moved = False
            for source in sorted(large, key=lambda c: -len(c.members)):
                for member_id in list(source.members):
                    camper = campers_by_id[member_id]
                    if not can_place(
                        camper,
                        target,
                        campers_by_id,
                        max_size,
                        max_disability,
                        max_same_school,
                        strict_grades,
                        strict_grade_span,
                    ):
                        continue
                    if len(source.members) - 1 < min_size:
                        continue
                    source.members.remove(member_id)
                    target.members.append(member_id)
                    # Rebuild both cabins to keep counters correct.
                    for c in (source, target):
                        c.disability_count = 0
                        c.school_counts = Counter()
                        c.component_counts = Counter()
                        c.min_grade = None
                        c.max_grade = None
                        member_copy = list(c.members)
                        c.members = []
                        for mid in member_copy:
                            place_camper(campers_by_id[mid], c)
                    changed = True
                    moved = True
                    break
                if moved:
                    break
        if not changed:
            break

    for c in cabins:
        if c.is_open and 0 < len(c.members) < min_size:
            warnings.append(
                {
                    "level": "warning",
                    "type": "underfilled-cabin",
                    "message": f"{c.week} {c.cabin_id} has {len(c.members)} campers (<{min_size}).",
                }
            )


def resolve_roommates_for_week(campers: List[Camper], config: dict):
    threshold = config["matching"]["name_fuzzy_threshold"]
    searchable = [
        (
            c.camper_id,
            c.full_name,
            normalize_text(c.first_name),
            normalize_text(c.last_name),
            c.gender,
        )
        for c in campers
    ]
    by_id = {c.camper_id: c for c in campers}
    if not searchable:
        return

    for camper in campers:
        matched = []
        resolutions = []
        for token in camper.roommate_tokens:
            t = normalize_text(token)
            if not t:
                continue
            token_parts = t.split()
            t_first = token_parts[0] if token_parts else ""
            t_last = token_parts[-1] if token_parts else ""

            best_id = None
            best_score = -1.0
            for cid, full_name, c_first, c_last, c_gender in searchable:
                if cid == camper.camper_id:
                    continue
                # Hard rule: only match roommate requests within the same gender.
                if c_gender != camper.gender:
                    continue
                score = max(
                    fuzz.WRatio(t, full_name),
                    fuzz.partial_ratio(t, full_name),
                    fuzz.token_set_ratio(t, full_name),
                )
                # Strongly reward first/last similarity for misspelled names.
                if t_first:
                    if t_first == c_first:
                        score += 12
                    else:
                        score += max(0, (fuzz.ratio(t_first, c_first) - 80) * 0.4)
                if t_last:
                    if t_last == c_last:
                        score += 10
                    else:
                        score += max(0, (fuzz.ratio(t_last, c_last) - 80) * 0.45)
                if t in full_name or full_name in t:
                    score += 8
                if score > best_score:
                    best_score = score
                    best_id = cid

            dynamic_threshold = min(threshold, 65)
            if best_id is None or best_score < dynamic_threshold:
                resolutions.append(
                    {
                        "requested": token,
                        "matched_id": None,
                        "matched_name": None,
                    }
                )
                continue
            if best_id in matched:
                resolutions.append(
                    {
                        "requested": token,
                        "matched_id": None,
                        "matched_name": None,
                    }
                )
                continue
            matched.append(best_id)
            matched_name = by_id[best_id].full_name if best_id in by_id else None
            resolutions.append(
                {
                    "requested": token,
                    "matched_id": best_id,
                    "matched_name": matched_name,
                }
            )
        camper.roommate_ids = matched[: config["max_roommate_requests_per_camper"]]
        camper.roommate_resolution = resolutions[: config["max_roommate_requests_per_camper"]]


def build_components(campers: List[Camper]):
    uf = UnionFind()
    by_id = {c.camper_id: c for c in campers}
    for camper in campers:
        for rid in camper.roommate_ids:
            if rid in by_id:
                uf.union(camper.camper_id, rid)
    for camper in campers:
        camper.component_id = uf.find(camper.camper_id)


def parse_camper_rows(df: pd.DataFrame, config: dict) -> List[Camper]:
    m = config["campers"]
    week_col = config["week_column"]
    regex = config["roommate_split_regex"]
    max_rr = config["max_roommate_requests_per_camper"]
    rows = []
    for i, row in df.iterrows():
        first = str(row.get(m["first_name"], "")).strip()
        last = str(row.get(m["last_name"], "")).strip()
        full_name = normalize_text(f"{first} {last}")
        if not first and not last:
            continue
        grade = parse_grade_value(row.get(m["grade"]), default=-1)
        if grade < 0:
            continue
        camper = Camper(
            camper_id=f"C{i+1}",
            week=str(row.get(week_col, "")).strip() or "Week-Unknown",
            first_name=first,
            last_name=last,
            full_name=full_name,
            gender=normalize_gender(row.get(m["gender"])),
            grade=grade,
            school_raw=str(row.get(m["school"], "")).strip(),
            school="",
            disability=disability_flag(row.get(m["disability_flag"])),
            disability_raw="" if pd.isna(row.get(m["disability_flag"])) else str(row.get(m["disability_flag"])).strip(),
            roommate_text=str(row.get(m["roommate_requests"], "")).strip(),
            roommate_tokens=split_tokens(str(row.get(m["roommate_requests"], "")), regex, max_rr),
        )
        rows.append(camper)
    return rows


def assign_campers(campers_df: pd.DataFrame, config: dict):
    warnings = []
    campers = parse_camper_rows(campers_df, config)
    if not campers:
        empty_pack = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        return empty_pack, pd.DataFrame(columns=["level", "type", "message"])
    school_threshold = config["matching"]["school_fuzzy_threshold"]
    school_map = canonicalize_schools(
        [c.school_raw for c in campers],
        school_threshold,
        config["cabins"]["other_school_labels"],
    )
    for c in campers:
        c.school = school_map.get(normalize_text(c.school_raw), "__OTHER__")

    by_week: Dict[str, List[Camper]] = defaultdict(list)
    for c in campers:
        by_week[c.week].append(c)

    assignment_rows = []
    summary_rows = []
    audit_rows = []

    for week, week_campers in sorted(by_week.items(), key=lambda x: x[0]):
        resolve_roommates_for_week(week_campers, config)
        build_components(week_campers)
        by_id = {c.camper_id: c for c in week_campers}

        female_group = [c for c in week_campers if c.gender == "Female"]
        male_group = [c for c in week_campers if c.gender == "Male"]
        unknown_group = [c for c in week_campers if c.gender not in {"Female", "Male"}]

        cabins = build_cabins_for_week(
            week=week,
            total_cabins=config["cabins"]["total_per_week"],
            female_count=len(female_group),
            male_count=len(male_group),
            min_per_cabin=config["cabins"]["min_per_open_cabin"],
            max_per_cabin=config["cabins"]["max_per_cabin"],
        )

        female_cabins = [c for c in cabins if c.gender == "Female"]
        male_cabins = [c for c in cabins if c.gender == "Male"]
        allow_grade_relaxation = bool(config["cabins"].get("allow_grade_relaxation", True))

        unassigned_f = assign_group(
            female_group, female_cabins, by_id, config, warnings, grade_strict=True
        )
        if allow_grade_relaxation:
            unassigned_f = assign_group(
                unassigned_f, female_cabins, by_id, config, warnings, grade_strict=False
            )
        unassigned_m = assign_group(
            male_group, male_cabins, by_id, config, warnings, grade_strict=True
        )
        if allow_grade_relaxation:
            unassigned_m = assign_group(
                unassigned_m, male_cabins, by_id, config, warnings, grade_strict=False
            )

        rebalance_min_size(cabins, by_id, config, warnings)
        improve_roommate_fulfillment(
            cabins,
            by_id,
            config,
            enforce_grade_rules=(config["cabins"]["strict_adjacent_grades"] and not allow_grade_relaxation),
            max_passes=4,
        )

        assigned_ids = set()
        for cabin in cabins:
            for cid in cabin.members:
                assigned_ids.add(cid)
                camper = by_id[cid]
                request_count = len(camper.roommate_tokens)
                fulfilled_count = sum(1 for rid in camper.roommate_ids if rid in set(cabin.members))
                unfulfilled_registered = max(0, len(camper.roommate_ids) - fulfilled_count)
                # Requested names that we couldn't match to any registered camper.
                unmatched_unregistered = max(0, request_count - len(camper.roommate_ids))
                status_emojis = ""
                status_detail = []
                if request_count > 0:
                    status_emojis = (
                        ("🟢" * fulfilled_count)
                        + ("🔴" * unfulfilled_registered)
                        + ("⚫️" * unmatched_unregistered)
                    )
                    for res in camper.roommate_resolution:
                        if not res.get("matched_id"):
                            status_detail.append(
                                {
                                    "emoji": "⚫️",
                                    "requested": res.get("requested", ""),
                                    "target": res.get("requested", ""),
                                    "status": "requested camper not found in registration",
                                }
                            )
                            continue
                        in_same_cabin = res["matched_id"] in set(cabin.members)
                        if in_same_cabin:
                            status_detail.append(
                                {
                                    "emoji": "🟢",
                                    "requested": res.get("requested", ""),
                                    "target": res.get("matched_name", ""),
                                    "matched_id": res.get("matched_id", ""),
                                    "status": "request fulfilled",
                                }
                            )
                        else:
                            status_detail.append(
                                {
                                    "emoji": "🔴",
                                    "requested": res.get("requested", ""),
                                    "target": res.get("matched_name", ""),
                                    "matched_id": res.get("matched_id", ""),
                                    "status": "requested camper assigned to a different cabin",
                                }
                            )
                assignment_rows.append(
                    {
                        "Week": week,
                        "Cabin": cabin.cabin_id,
                        "Cabin Gender": cabin.gender,
                        "Open Cabin": "Yes" if cabin.is_open else "No",
                        "Camper ID": camper.camper_id,
                        "Camper Name": f"{camper.first_name} {camper.last_name}".strip(),
                        "Gender": camper.gender,
                        "Grade": camper.grade,
                        "School (normalized)": camper.school,
                        "Disability Flag": "Yes" if camper.disability else "No",
                        "Disability Raw": camper.disability_raw,
                        "Roommate Request Raw": camper.roommate_text,
                        "Resolved Roommates": ", ".join(camper.roommate_ids),
                        "Roommate Request Count": request_count,
                        "Roommate Fulfilled Count": fulfilled_count,
                        "Roommate Unfulfilled Registered": unfulfilled_registered,
                        "Roommate Requested Not Registered": unmatched_unregistered,
                        "Roommate Status Emojis": status_emojis,
                        "Roommate Status Detail": status_detail,
                    }
                )
            summary_rows.append(
                {
                    "Week": week,
                    "Cabin": cabin.cabin_id,
                    "Cabin Gender": cabin.gender,
                    "Open Cabin": "Yes" if cabin.is_open else "No",
                    "Campers": len(cabin.members),
                    "Disability Count": cabin.disability_count,
                    "Distinct Schools (excluding Other)": len(cabin.school_counts),
                    "Grade Range": ""
                    if cabin.min_grade is None
                    else f"{cabin.min_grade}-{cabin.max_grade}",
                }
            )

        for camper in week_campers:
            resolved_names = [by_id[r].full_name for r in camper.roommate_ids if r in by_id]
            matched_count = sum(1 for rid in camper.roommate_ids if rid in assigned_ids)
            audit_rows.append(
                {
                    "Week": week,
                    "Camper ID": camper.camper_id,
                    "Camper Name": f"{camper.first_name} {camper.last_name}".strip(),
                    "Gender": camper.gender,
                    "Grade": camper.grade,
                    "School Normalized": camper.school,
                    "Disability": "Yes" if camper.disability else "No",
                    "Requested Roommates Parsed": ", ".join(camper.roommate_tokens),
                    "Resolved Roommate IDs": ", ".join(camper.roommate_ids),
                    "Resolved Roommate Names": ", ".join(resolved_names),
                    "Roommate Matches Found": matched_count,
                }
            )

        for camper in unassigned_f + unassigned_m + unknown_group:
            if camper in unknown_group:
                reason = "missing or invalid gender value"
            else:
                target_cabins = female_cabins if camper.gender == "Female" else male_cabins
                reason = explain_unassigned_reason(
                    camper,
                    target_cabins,
                    config,
                    consider_grade_rule=False,
                )
            request_count = len(camper.roommate_tokens)
            status_detail = []
            status_emojis = ""
            if request_count > 0:
                for res in camper.roommate_resolution:
                    if not res.get("matched_id"):
                        status_detail.append(
                            {
                                "emoji": "⚫️",
                                "requested": res.get("requested", ""),
                                "target": res.get("requested", ""),
                                "status": "requested camper not found in registration",
                            }
                        )
                        continue
                    matched_id = res.get("matched_id")
                    matched_name = res.get("matched_name", "")
                    if matched_id in assigned_ids:
                        status_detail.append(
                            {
                                "emoji": "🔴",
                                "requested": res.get("requested", ""),
                                "target": matched_name,
                                "matched_id": matched_id,
                                "status": "requested camper assigned to a different cabin",
                            }
                        )
                    else:
                        status_detail.append(
                            {
                                "emoji": "🔴",
                                "requested": res.get("requested", ""),
                                "target": matched_name,
                                "matched_id": matched_id,
                                "status": "requested camper is also currently unassigned",
                            }
                        )
                status_emojis = "".join([str(d.get("emoji", "")) for d in status_detail])
            warnings.append(
                {
                    "level": "error",
                    "type": "unassigned-camper",
                    "week": week,
                    "camper_id": camper.camper_id,
                    "camper_name": f"{camper.first_name} {camper.last_name}".strip(),
                    "gender": camper.gender,
                    "grade": camper.grade,
                    "disability_flag": "Yes" if camper.disability else "No",
                    "reason": reason,
                    "roommate_status_emojis": status_emojis,
                    "roommate_status_detail": status_detail,
                    "message": (
                        f"{week}: {camper.first_name} {camper.last_name} could not be assigned. "
                        f"Grade: {camper.grade}. "
                        f"Disability: {'Yes' if camper.disability else 'No'}. "
                        f"Reason: {reason}."
                    ),
                }
            )

    return (
        pd.DataFrame(assignment_rows),
        pd.DataFrame(summary_rows),
        pd.DataFrame(audit_rows),
    ), pd.DataFrame(warnings)


def split_list(text: str) -> List[str]:
    if not text:
        return []
    parts = [normalize_text(x) for x in re.split(r"[,;/&]|\band\b", str(text), flags=re.IGNORECASE)]
    return [x for x in parts if x]


def split_availability_list(text: str) -> List[str]:
    raw = normalize_text(text)
    if not raw or raw in {"nan", "none", "n/a"}:
        return []
    raw = re.sub(r"\s+(and|&)\s+", ",", raw, flags=re.IGNORECASE)
    raw = raw.replace(";", ",").replace("/", ",").replace("|", ",")
    raw = raw.replace("\n", ",")
    parts = [normalize_text(x) for x in raw.split(",")]
    cleaned = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            cleaned.append(p)
    return list(dict.fromkeys(cleaned))


def split_name_list(text: str, max_items: int = 8) -> List[str]:
    raw = normalize_text(text)
    if not raw or raw in {"nan", "none", "n/a"}:
        return []
    raw = re.sub(r"(^|\s)\d+\s*[\.\)\-:]\s*", ", ", raw)
    raw = re.sub(r"\s*-\s*(?=\d+\s*[\.\)\-:])", ", ", raw)
    raw = re.sub(r"\s+(and|&)\s+", ",", raw, flags=re.IGNORECASE)
    raw = raw.replace(";", ",").replace("/", ",").replace("|", ",")
    raw = re.sub(r"\.\s+(?=[a-z])", ", ", raw)
    tokens = []
    seen = set()
    for part in raw.split(","):
        p = normalize_text(part)
        p = re.sub(r"^\d+\s*[\.\)\-:]\s*", "", p)
        p = re.sub(r"[^a-z0-9\s\-']", " ", p).strip()
        p = re.sub(r"\s+", " ", p)
        if not p or p in seen:
            continue
        seen.add(p)
        tokens.append(p)
        if len(tokens) >= max_items:
            break
    return tokens


def parse_friend_ids(
    cdf: pd.DataFrame, friend_col: str, name_threshold: int
) -> Tuple[List[List[str]], List[List[str]]]:
    names = cdf["Full Name"].fillna("").astype(str).tolist()
    name_norms = [normalize_text(x) for x in names]
    ids = cdf["Counselor ID"].fillna("").astype(str).tolist()
    all_friend_ids: List[List[str]] = []
    all_friend_unmatched: List[List[str]] = []
    for idx, row in cdf.iterrows():
        mine = str(row.get("Counselor ID", ""))
        raw = row.get(friend_col, "")
        tokens = split_name_list(raw)
        resolved = []
        unresolved = []
        seen = set()
        for token in tokens:
            match = process.extractOne(token, name_norms, scorer=fuzz.token_set_ratio)
            if not match or match[1] < name_threshold:
                unresolved.append(token)
                continue
            matched_idx = match[2]
            matched_id = ids[matched_idx]
            if not matched_id or matched_id == mine or matched_id in seen:
                continue
            seen.add(matched_id)
            resolved.append(matched_id)
        all_friend_ids.append(resolved)
        all_friend_unmatched.append(unresolved)
    return all_friend_ids, all_friend_unmatched


def is_available_for_camp(camp: str, avail_tokens: List[str], raw_availability: str) -> bool:
    camp_norm = normalize_text(camp)
    if not camp_norm:
        return False
    normalized_tokens = [normalize_text(t) for t in (avail_tokens or []) if normalize_text(t)]
    if not normalized_tokens:
        normalized_tokens = split_availability_list(raw_availability)
    # Business rule: blank availability means available for any camp.
    if not normalized_tokens:
        raw = normalize_text(raw_availability)
        if raw in {"", "nan", "none", "n/a", "na", "null", "nat", "undefined"}:
            return True
    for token in normalized_tokens:
        if same_camp_session(camp_norm, token):
            return True
    return False


def same_camp_session(a: str, b: str) -> bool:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return False
    def family(text: str) -> str:
        if re.search(r"\b(sky\s*games|sg)\b", text):
            return "sky games"
        if re.search(r"\b(western\s*adventure\s*camp|western\s*camp|wac|wc)\b", text):
            return "western camp"
        if re.search(r"\b(sky\s*camp|sc)\b", text):
            return "sky camp"
        return ""

    def session_num(text: str) -> str:
        m = re.search(r"\b(?:session|sess|s)\s*[-:]?\s*(\d+)\b", text)
        if not m:
            m = re.search(r"\b(?:camp|games)\s*(\d+)\b", text)
        return m.group(1) if m else ""

    a_family = family(a_norm)
    b_family = family(b_norm)
    a_num = session_num(a_norm)
    b_num = session_num(b_norm)
    if a_num and b_num and a_num != b_num:
        return False
    if a_family and b_family and a_family != b_family:
        return False
    if a_family and b_family and a_num and b_num:
        return True
    if a_norm == b_norm:
        return True
    if a_norm in b_norm or b_norm in a_norm:
        return True
    return fuzz.token_set_ratio(a_norm, b_norm) >= 92


def preference_score(camp: str, row: pd.Series, m: dict, pref_scores: dict) -> int:
    c = normalize_text(camp)
    p1 = normalize_text(row.get(m["preference_1"], ""))
    p2 = normalize_text(row.get(m["preference_2"], ""))
    p3 = normalize_text(row.get(m["preference_3"], ""))
    if same_camp_session(c, p1):
        return int(pref_scores.get("1", 100))
    if same_camp_session(c, p2):
        return int(pref_scores.get("2", 70))
    if same_camp_session(c, p3):
        return int(pref_scores.get("3", 40))
    return 0


def preference_rank(camp: str, row: pd.Series, m: dict) -> str:
    c = normalize_text(camp)
    p1 = normalize_text(row.get(m["preference_1"], ""))
    p2 = normalize_text(row.get(m["preference_2"], ""))
    p3 = normalize_text(row.get(m["preference_3"], ""))
    if same_camp_session(c, p1):
        return "1"
    if same_camp_session(c, p2):
        return "2"
    if same_camp_session(c, p3):
        return "3"
    return "none"


def parse_capacity(value) -> int:
    raw = normalize_text(value)
    if not raw:
        # Conservative default: if no willingness value is provided,
        # assume counselor is willing to work 1 camp.
        return 1
    if "as many" in raw or raw in {"all", "any", "unlimited", "no limit"}:
        return 999
    word_match = re.search(r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b", raw)
    if word_match:
        return NUMBER_WORDS[word_match.group(1)]
    n = to_int(raw, default=-999)
    if n == -999:
        return 1
    return max(0, n)


def is_unlimited_capacity(value) -> bool:
    raw = normalize_text(value)
    if not raw:
        return False
    return "as many" in raw or raw in {"all", "any", "unlimited", "no limit"}


def assign_counselors(
    counselors_df: pd.DataFrame,
    camp_targets_df: pd.DataFrame,
    config: dict,
    single_camp_only: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if counselors_df.empty or camp_targets_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    m = config["counselors"]
    pref_scores = config["counselor_assignment"]["preference_scores"]
    friend_bonus = int(config["counselor_assignment"]["friend_bonus"])

    cdf = counselors_df.copy()
    cdf["Counselor ID"] = [f"S{i+1}" for i in range(len(cdf))]
    cdf["Full Name"] = (
        cdf[m["first_name"]].fillna("").astype(str).str.strip()
        + " "
        + cdf[m["last_name"]].fillna("").astype(str).str.strip()
    ).str.strip()
    cdf["Gender Normalized"] = cdf[m["gender"]].apply(normalize_gender)
    cdf["Availability Raw"] = cdf[m["availability"]].fillna("").astype(str)
    cdf["Avail List"] = cdf["Availability Raw"].apply(split_availability_list)
    name_threshold = int(config.get("matching", {}).get("name_fuzzy_threshold", 82))
    friend_ids, friend_unmatched = parse_friend_ids(cdf, m["friend_requests"], name_threshold)
    cdf["Friend IDs"] = friend_ids
    cdf["Friend Unmatched Names"] = friend_unmatched
    requested_by_map = defaultdict(list)
    for _, row in cdf.iterrows():
        my_id = str(row.get("Counselor ID", "")).strip()
        for fid in row.get("Friend IDs", []):
            if fid and fid != my_id:
                requested_by_map[fid].append(my_id)
    cdf["Requested By IDs"] = cdf["Counselor ID"].astype(str).map(
        lambda cid: requested_by_map.get(str(cid), [])
    )
    cdf["Remaining Capacity"] = cdf.get(
        m.get("willing_camps", ""), pd.Series([999] * len(cdf))
    ).apply(parse_capacity)
    cdf["Max Capacity"] = cdf["Remaining Capacity"]
    if single_camp_only:
        cdf["Remaining Capacity"] = 1
        cdf["Max Capacity"] = 1
    cdf["IsUnlimited"] = cdf.get(
        m.get("willing_camps", ""), pd.Series([""] * len(cdf))
    ).apply(is_unlimited_capacity)
    cdf["Assigned Count"] = 0

    camp_rows = []
    camp_order: List[str] = []
    camp_seen = set()
    slot_counts_by_camp = defaultdict(lambda: {"Female": 0, "Male": 0, "Any": 0})
    warnings = []
    assignments_by_camp = defaultdict(set)
    assigned_rows = []

    required_cols = {"Camp", "Target Total"}
    if not required_cols.issubset(set(camp_targets_df.columns)):
        warnings.append(
            {
                "level": "error",
                "type": "camp-target-columns",
                "message": "camp_targets sheet must include columns: Camp and Target Total",
            }
        )
        return pd.DataFrame(), pd.DataFrame(warnings)

    for _, row in camp_targets_df.iterrows():
        camp = str(row.get("Camp", "")).strip()
        if not camp:
            continue
        if camp not in camp_seen:
            camp_seen.add(camp)
            camp_order.append(camp)
        total = max(0, to_int(row.get("Target Total"), default=0))
        female_target = max(0, to_int(row.get("Target Female"), default=0))
        male_target = max(0, to_int(row.get("Target Male"), default=0))
        any_target = max(0, total - female_target - male_target)
        slot_counts_by_camp[camp]["Female"] += female_target
        slot_counts_by_camp[camp]["Male"] += male_target
        slot_counts_by_camp[camp]["Any"] += any_target

    def add_slots_round_robin(slot_type: str):
        remaining = {
            camp: int(slot_counts_by_camp[camp].get(slot_type, 0))
            for camp in camp_order
        }
        while any(v > 0 for v in remaining.values()):
            for camp in camp_order:
                if remaining.get(camp, 0) <= 0:
                    continue
                camp_rows.append((camp, slot_type))
                remaining[camp] -= 1

    # Interleave slots across camps instead of filling camp-by-camp.
    # This prevents early camps from consuming all one-camp counselors.
    add_slots_round_robin("Female")
    add_slots_round_robin("Male")
    add_slots_round_robin("Any")

    if not camp_rows:
        warnings.append(
            {
                "level": "error",
                "type": "empty-camp-targets",
                "message": "No valid camp target rows were found (Camp + Target Total > 0).",
            }
        )
        return pd.DataFrame(), pd.DataFrame(warnings)

    def build_candidates(
        camp: str,
        gender_need: str,
        assigned_this_round: set,
        enforce_round_limit: bool,
        enforce_gender_need: bool = True,
        allow_capacity_overage: bool = False,
        max_capacity_overage: int = 0,
        unlimited_only: bool = False,
    ) -> List[Tuple[int, int]]:
        candidates = []
        for idx, row in cdf.iterrows():
            cid = str(row["Counselor ID"])
            if unlimited_only and not bool(row.get("IsUnlimited", False)):
                continue
            if row["Remaining Capacity"] <= 0:
                if not allow_capacity_overage:
                    continue
                max_capacity = int(row.get("Max Capacity", 0))
                assigned_count = int(row["Assigned Count"])
                if assigned_count >= (max_capacity + max_capacity_overage):
                    continue
            if cid in assignments_by_camp[camp]:
                continue
            if enforce_round_limit and cid in assigned_this_round:
                continue
            avail = row["Avail List"]
            pref, pref_match = score_and_rank_for_mode(camp, row)
            if single_camp_only:
                p1_raw = normalize_text(row.get(m["preference_1"], ""))
                if p1_raw and pref_match != "1":
                    continue
            avail_ok = is_available_for_camp(camp, avail, row["Availability Raw"])
            # Business rule: a stated preference also implies eligibility for that camp.
            if not avail_ok and pref_match == "none":
                continue
            if (
                enforce_gender_need
                and gender_need in {"Female", "Male"}
                and row["Gender Normalized"] != gender_need
            ):
                continue
            # Priority order:
            # 1) availability eligibility (hard gate above)
            # 2) preference rank match
            # 3) willingness count (max camps they can work)
            pref_priority = {"1": 3, "2": 2, "3": 1}.get(pref_match, 0)
            willingness = int(row.get("Max Capacity", row["Remaining Capacity"]))

            # Tie-breakers only (do not override primary priority ordering).
            f_bonus = 0
            for fid in row["Friend IDs"]:
                if fid and fid in assignments_by_camp[camp]:
                    # Keep friend influence mild.
                    f_bonus += min(friend_bonus, 2)
            assigned_count = int(row["Assigned Count"])
            fairness_bonus = max(0, 12 - (assigned_count * 4))

            score = (
                (pref_priority * 1_000_000)
                + (max(0, willingness) * 1_000)
                + (max(0, pref) * 10)
                + max(0, f_bonus)
                + max(0, fairness_bonus)
            )
            candidates.append((score, idx))
        return candidates

    def score_and_rank_for_mode(camp: str, row: pd.Series) -> Tuple[int, str]:
        if single_camp_only:
            p1 = normalize_text(row.get(m["preference_1"], ""))
            rank = "1" if same_camp_session(normalize_text(camp), p1) else "none"
            return (int(pref_scores.get("1", 100)) if rank == "1" else 0), rank
        return preference_score(camp, row, m, pref_scores), preference_rank(camp, row, m)

    # Round-robin passes: give each counselor at most one camp per pass first.
    remaining_slots = list(camp_rows)
    if remaining_slots:
        cap_series = pd.to_numeric(cdf["Remaining Capacity"], errors="coerce").fillna(0)
        cap_series = cap_series.clip(lower=0, upper=len(remaining_slots))
        max_rounds = max(1, int(cap_series.max()))
    else:
        max_rounds = 0
    max_rounds = min(max_rounds, max(1, len(remaining_slots)))

    for _ in range(max_rounds):
        if not remaining_slots:
            break
        assigned_this_round = set()
        next_remaining = []
        progress = False
        for camp, gender_need in remaining_slots:
            candidates = build_candidates(
                camp,
                gender_need,
                assigned_this_round,
                enforce_round_limit=True,
                enforce_gender_need=True,
                allow_capacity_overage=False,
                max_capacity_overage=0,
            )
            if not candidates:
                next_remaining.append((camp, gender_need))
                continue
            candidates.sort(key=lambda x: (-x[0], str(cdf.loc[x[1], "Full Name"])))
            chosen_idx = candidates[0][1]
            cid = str(cdf.at[chosen_idx, "Counselor ID"])
            cdf.at[chosen_idx, "Remaining Capacity"] = (
                cdf.at[chosen_idx, "Remaining Capacity"] - 1
            )
            cdf.at[chosen_idx, "Assigned Count"] = cdf.at[chosen_idx, "Assigned Count"] + 1
            assigned_this_round.add(cid)
            assignments_by_camp[camp].add(cid)
            pref_score_val, pref_rank_val = score_and_rank_for_mode(camp, cdf.loc[chosen_idx])
            assigned_rows.append(
                {
                    "Camp": camp,
                    "Slot Gender Need": gender_need,
                    "Counselor ID": cid,
                    "Counselor Name": cdf.at[chosen_idx, "Full Name"],
                    "Gender": cdf.at[chosen_idx, "Gender Normalized"],
                    "Email": cdf.at[chosen_idx, m["email"]],
                    "Preference Score": pref_score_val,
                    "Preference Match": pref_rank_val,
                    "Friend IDs": cdf.at[chosen_idx, "Friend IDs"],
                    "Friend Unmatched Names": cdf.at[chosen_idx, "Friend Unmatched Names"],
                    "Requested By IDs": cdf.at[chosen_idx, "Requested By IDs"],
                }
            )
            progress = True
        remaining_slots = next_remaining
        if not progress:
            break

    # Final fill pass: allow multiple assignments per pass when needed.
    still_unfilled = []
    for camp, gender_need in remaining_slots:
        candidates = build_candidates(
            camp,
            gender_need,
            assigned_this_round=set(),
            enforce_round_limit=False,
            enforce_gender_need=True,
            allow_capacity_overage=False,
            max_capacity_overage=0,
        )
        if not candidates:
            still_unfilled.append((camp, gender_need))
            continue
        candidates.sort(key=lambda x: (-x[0], str(cdf.loc[x[1], "Full Name"])))
        chosen_idx = candidates[0][1]
        cid = str(cdf.at[chosen_idx, "Counselor ID"])
        cdf.at[chosen_idx, "Remaining Capacity"] = cdf.at[chosen_idx, "Remaining Capacity"] - 1
        cdf.at[chosen_idx, "Assigned Count"] = cdf.at[chosen_idx, "Assigned Count"] + 1
        assignments_by_camp[camp].add(cid)
        pref_score_val, pref_rank_val = score_and_rank_for_mode(camp, cdf.loc[chosen_idx])
        assigned_rows.append(
            {
                "Camp": camp,
                "Slot Gender Need": gender_need,
                "Counselor ID": cid,
                "Counselor Name": cdf.at[chosen_idx, "Full Name"],
                "Gender": cdf.at[chosen_idx, "Gender Normalized"],
                "Email": cdf.at[chosen_idx, m["email"]],
                "Preference Score": pref_score_val,
                "Preference Match": pref_rank_val,
                "Friend IDs": cdf.at[chosen_idx, "Friend IDs"],
                "Friend Unmatched Names": cdf.at[chosen_idx, "Friend Unmatched Names"],
                "Requested By IDs": cdf.at[chosen_idx, "Requested By IDs"],
            }
        )

    # Soft overage pass: allow counselors to exceed willing-camps by +2
    # if open slots still remain. Availability still enforced.
    if still_unfilled:
        unresolved = list(still_unfilled)
        still_unfilled = []
        for camp, gender_need in unresolved:
            candidates = build_candidates(
                camp,
                gender_need,
                assigned_this_round=set(),
                enforce_round_limit=False,
                enforce_gender_need=True,
                allow_capacity_overage=True,
                max_capacity_overage=2,
            )
            if not candidates:
                still_unfilled.append((camp, gender_need))
                continue
            candidates.sort(key=lambda x: (-x[0], str(cdf.loc[x[1], "Full Name"])))
            chosen_idx = candidates[0][1]
            cid = str(cdf.at[chosen_idx, "Counselor ID"])
            cdf.at[chosen_idx, "Remaining Capacity"] = cdf.at[chosen_idx, "Remaining Capacity"] - 1
            cdf.at[chosen_idx, "Assigned Count"] = cdf.at[chosen_idx, "Assigned Count"] + 1
            assignments_by_camp[camp].add(cid)
            pref_score_val, pref_rank_val = score_and_rank_for_mode(camp, cdf.loc[chosen_idx])
            assigned_rows.append(
                {
                    "Camp": camp,
                    "Slot Gender Need": gender_need,
                    "Counselor ID": cid,
                    "Counselor Name": cdf.at[chosen_idx, "Full Name"],
                    "Gender": cdf.at[chosen_idx, "Gender Normalized"],
                    "Email": cdf.at[chosen_idx, m["email"]],
                    "Preference Score": pref_score_val,
                    "Preference Match": pref_rank_val,
                    "Friend IDs": cdf.at[chosen_idx, "Friend IDs"],
                    "Friend Unmatched Names": cdf.at[chosen_idx, "Friend Unmatched Names"],
                    "Requested By IDs": cdf.at[chosen_idx, "Requested By IDs"],
                }
            )

    # Unlimited-capacity preference pass:
    # if open slots still remain, prioritize counselors who explicitly said
    # "As many as you need" before final warning generation.
    if still_unfilled:
        unresolved = list(still_unfilled)
        still_unfilled = []
        for camp, gender_need in unresolved:
            candidates = build_candidates(
                camp,
                gender_need,
                assigned_this_round=set(),
                enforce_round_limit=False,
                enforce_gender_need=True,
                allow_capacity_overage=False,
                max_capacity_overage=0,
                unlimited_only=True,
            )
            if not candidates:
                still_unfilled.append((camp, gender_need))
                continue
            candidates.sort(key=lambda x: (-x[0], str(cdf.loc[x[1], "Full Name"])))
            chosen_idx = candidates[0][1]
            cid = str(cdf.at[chosen_idx, "Counselor ID"])
            cdf.at[chosen_idx, "Remaining Capacity"] = cdf.at[chosen_idx, "Remaining Capacity"] - 1
            cdf.at[chosen_idx, "Assigned Count"] = cdf.at[chosen_idx, "Assigned Count"] + 1
            assignments_by_camp[camp].add(cid)
            pref_score_val, pref_rank_val = score_and_rank_for_mode(camp, cdf.loc[chosen_idx])
            assigned_rows.append(
                {
                    "Camp": camp,
                    "Slot Gender Need": gender_need,
                    "Counselor ID": cid,
                    "Counselor Name": cdf.at[chosen_idx, "Full Name"],
                    "Gender": cdf.at[chosen_idx, "Gender Normalized"],
                    "Email": cdf.at[chosen_idx, m["email"]],
                    "Preference Score": pref_score_val,
                    "Preference Match": pref_rank_val,
                    "Friend IDs": cdf.at[chosen_idx, "Friend IDs"],
                    "Friend Unmatched Names": cdf.at[chosen_idx, "Friend Unmatched Names"],
                    "Requested By IDs": cdf.at[chosen_idx, "Requested By IDs"],
                }
            )

    # Aggregate unfilled slots so warning output is actionable (not hundreds of rows).
    unfilled_counts = defaultdict(int)
    for camp, gender_need in still_unfilled:
        unfilled_counts[(camp, gender_need)] += 1
    for (camp, gender_need), missing_count in sorted(unfilled_counts.items()):
        warnings.append(
            {
                "level": "warning",
                "type": "unfilled-camp-slot",
                "camp": camp,
                "slot_gender_need": gender_need,
                "unfilled_count": int(missing_count),
                "message": f"No counselor found for {camp} ({gender_need}) x{missing_count}.",
            }
        )

    return pd.DataFrame(assigned_rows), pd.DataFrame(warnings)


def ensure_files(args):
    config_path = Path(args.config)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing config file: {config_path}\n"
            "Create it from config.template.json first, then run again."
        )
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_template_workbook(config: dict, output_path: str):
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

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame(columns=campers_headers).to_excel(
            writer, index=False, sheet_name=config["campers_sheet"]
        )
        pd.DataFrame(columns=counselors_headers).to_excel(
            writer, index=False, sheet_name=config["counselors_sheet"]
        )
        pd.DataFrame(columns=camp_targets_headers).to_excel(
            writer, index=False, sheet_name=config["camp_targets_sheet"]
        )


def main():
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing config file: {config_path}\n"
            "Create it from config.template.json first, then run again."
        )
    config = load_config(args.config)

    if args.init_workbook:
        create_template_workbook(config, args.init_workbook)
        print(f"STEP 1 workbook created at: {args.init_workbook}")
        print("Now fill in camps, campers, and counselors, then run assignment.")
        return

    if not args.input or not args.output:
        raise ValueError("Provide --input and --output, or use --init-workbook.")
    ensure_files(args)

    xls = pd.ExcelFile(args.input)
    needed = [config["campers_sheet"], config["counselors_sheet"], config["camp_targets_sheet"]]
    missing = [s for s in needed if s not in xls.sheet_names]
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(
            "STEP 1: Add missing sheet(s) in input workbook before assigning: "
            f"{missing_str}"
        )

    campers_df = pd.read_excel(args.input, sheet_name=config["campers_sheet"])
    counselors_df = pd.read_excel(args.input, sheet_name=config["counselors_sheet"])
    camp_targets_df = pd.read_excel(args.input, sheet_name=config["camp_targets_sheet"])

    camper_pack, camper_warnings = assign_campers(campers_df, config)
    cabin_assignments_df, cabin_summary_df, camper_audit_df = camper_pack
    counselor_assignments_df, counselor_warnings_df = assign_counselors(
        counselors_df, camp_targets_df, config
    )

    warnings_df = pd.concat(
        [camper_warnings, counselor_warnings_df], ignore_index=True
    ) if not camper_warnings.empty or not counselor_warnings_df.empty else pd.DataFrame(
        columns=["level", "type", "message"]
    )

    metrics = [
        {"Metric": "Total cabin assignment rows", "Value": len(cabin_assignments_df)},
        {"Metric": "Open cabins", "Value": int((cabin_summary_df["Open Cabin"] == "Yes").sum()) if not cabin_summary_df.empty else 0},
        {"Metric": "Warnings", "Value": len(warnings_df)},
        {"Metric": "Counselor assignments", "Value": len(counselor_assignments_df)},
    ]
    metrics_df = pd.DataFrame(metrics)

    with pd.ExcelWriter(args.output, engine="openpyxl") as writer:
        cabin_assignments_df.to_excel(writer, index=False, sheet_name="cabin_assignments")
        cabin_summary_df.to_excel(writer, index=False, sheet_name="cabin_summary")
        camper_audit_df.to_excel(writer, index=False, sheet_name="camper_audit")
        counselor_assignments_df.to_excel(writer, index=False, sheet_name="counselor_assignments")
        warnings_df.to_excel(writer, index=False, sheet_name="warnings")
        metrics_df.to_excel(writer, index=False, sheet_name="metrics")

    print(f"Done. Output written to: {args.output}")
    if not warnings_df.empty:
        print(f"Warnings generated: {len(warnings_df)} (see 'warnings' sheet)")


if __name__ == "__main__":
    main()
