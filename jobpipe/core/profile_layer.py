from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from jobpipe.core.paths import JobPipePaths

PROFILE_LAYER_SCHEMA_VERSION = "jobpipe.profile-layer.v2"


class ResumeMaster(BaseModel):
    resume_master_id: str
    source_type: str
    source_ref: str
    default_language: str = "nb"
    role_record_ids: List[str] = Field(default_factory=list)
    project_record_ids: List[str] = Field(default_factory=list)
    skill_atom_ids: List[str] = Field(default_factory=list)
    narrative_profile_id: str
    updated_at: str = ""
    schema_version: str = PROFILE_LAYER_SCHEMA_VERSION
    source_provenance: Dict[str, Any] = Field(default_factory=dict)


class RoleRecord(BaseModel):
    role_record_id: str
    company: str
    title: str
    location: str = ""
    date_range: str = ""
    canonical_facts: Dict[str, str] = Field(default_factory=dict)
    role_variant_ids: List[str] = Field(default_factory=list)
    evidence_atom_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class RoleVariant(BaseModel):
    role_variant_id: str
    role_record_id: str
    label: str
    language: str = "nb"
    target_tags: List[str] = Field(default_factory=list)
    summary: str = ""
    preferred_evidence_atom_ids: List[str] = Field(default_factory=list)
    suppressed_evidence_atom_ids: List[str] = Field(default_factory=list)
    tone_profile: str = ""


class ProjectRecord(BaseModel):
    project_record_id: str
    name: str
    canonical_facts: Dict[str, str] = Field(default_factory=dict)
    project_variant_ids: List[str] = Field(default_factory=list)
    evidence_atom_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class ProjectVariant(BaseModel):
    project_variant_id: str
    project_record_id: str
    label: str
    language: str = "nb"
    target_tags: List[str] = Field(default_factory=list)
    summary: str = ""
    preferred_evidence_atom_ids: List[str] = Field(default_factory=list)


class EvidenceAtom(BaseModel):
    evidence_atom_id: str
    source_type: str
    source_id: str
    language: str = "nb"
    text: str
    tags: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    seniority_signals: List[str] = Field(default_factory=list)
    strength_score: int = Field(default=50, ge=0, le=100)
    approved: bool = True


class SkillAtom(BaseModel):
    skill_atom_id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    category: str = ""
    strength: int = Field(default=50, ge=0, le=100)
    evidence_atom_ids: List[str] = Field(default_factory=list)


class ContentLibrary(BaseModel):
    content_library_id: str
    resume_master_id: str
    role_variant_ids: List[str] = Field(default_factory=list)
    project_variant_ids: List[str] = Field(default_factory=list)
    evidence_atom_ids: List[str] = Field(default_factory=list)
    skill_atom_ids: List[str] = Field(default_factory=list)
    section_inventory: Dict[str, List[str]] = Field(default_factory=dict)
    schema_version: str = PROFILE_LAYER_SCHEMA_VERSION
    source_provenance: Dict[str, Any] = Field(default_factory=dict)


class SelectionRules(BaseModel):
    selection_rules_id: str
    resume_master_id: str
    default_role_variant_ids: List[str] = Field(default_factory=list)
    default_project_variant_ids: List[str] = Field(default_factory=list)
    featured_skill_atom_ids: List[str] = Field(default_factory=list)
    evidence_priority_ids: List[str] = Field(default_factory=list)
    preferred_section_order: List[str] = Field(default_factory=list)
    section_visibility: Dict[str, bool] = Field(default_factory=dict)
    max_items_per_section: Dict[str, int] = Field(default_factory=dict)
    schema_version: str = PROFILE_LAYER_SCHEMA_VERSION
    source_provenance: Dict[str, Any] = Field(default_factory=dict)


class LayoutProfile(BaseModel):
    layout_profile_id: str
    resume_master_id: str
    engine: str = "reactive-resume"
    template_key: str = "rr-json-resume-baseline"
    locale: str = "nb-NO"
    section_order: List[str] = Field(default_factory=list)
    visible_sections: List[str] = Field(default_factory=list)
    hidden_sections: List[str] = Field(default_factory=list)
    item_limits: Dict[str, int] = Field(default_factory=dict)
    page_settings: Dict[str, Any] = Field(default_factory=dict)
    rr_compat: Dict[str, Any] = Field(default_factory=dict)
    schema_version: str = PROFILE_LAYER_SCHEMA_VERSION
    source_provenance: Dict[str, Any] = Field(default_factory=dict)


class NarrativeProfile(BaseModel):
    narrative_profile_id: str
    voice_traits: List[str] = Field(default_factory=list)
    preferred_positioning: List[str] = Field(default_factory=list)
    do_not_claim: List[str] = Field(default_factory=list)
    language_preferences: str = ""
    operator_notes: str = ""
    source_provenance: Dict[str, Any] = Field(default_factory=dict)


class ProfileSnapshot(BaseModel):
    profile_snapshot_id: str
    resume_master_id: str
    target_roles: List[str] = Field(default_factory=list)
    domain_strengths: List[str] = Field(default_factory=list)
    seniority_profile: str = ""
    location_preferences: List[str] = Field(default_factory=list)
    core_skills: List[str] = Field(default_factory=list)
    core_evidence_atom_ids: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    source_provenance: Dict[str, Any] = Field(default_factory=dict)


class TargetingProfile(BaseModel):
    targeting_profile_id: str
    profile_snapshot_id: str
    allowed_geos: List[str] = Field(default_factory=list)
    blocked_geos: List[str] = Field(default_factory=list)
    target_title_patterns: List[str] = Field(default_factory=list)
    hard_no_title_patterns: List[str] = Field(default_factory=list)
    preferred_domains: List[str] = Field(default_factory=list)
    connector_policies: Dict[str, Any] = Field(default_factory=dict)
    source_provenance: Dict[str, Any] = Field(default_factory=dict)


class TriageProfile(BaseModel):
    triage_profile_id: str
    profile_snapshot_id: str
    role_summary: str = ""
    advantageous_match_hypotheses: List[str] = Field(default_factory=list)
    transferable_strengths: List[str] = Field(default_factory=list)
    skill_clusters: List[str] = Field(default_factory=list)
    must_not_miss_patterns: List[str] = Field(default_factory=list)
    evidence_atoms_compact: List[str] = Field(default_factory=list)
    source_provenance: Dict[str, Any] = Field(default_factory=dict)


class AuthoringProfile(BaseModel):
    authoring_profile_id: str
    profile_snapshot_id: str
    strongest_storylines: List[str] = Field(default_factory=list)
    selected_evidence_atom_ids: List[str] = Field(default_factory=list)
    work_history_refs: List[str] = Field(default_factory=list)
    project_refs: List[str] = Field(default_factory=list)
    value_prop_templates: List[str] = Field(default_factory=list)
    gap_handling_templates: List[str] = Field(default_factory=list)
    writing_constraints: List[str] = Field(default_factory=list)
    source_provenance: Dict[str, Any] = Field(default_factory=dict)


class ProfileLayerBundle(BaseModel):
    schema_version: str = PROFILE_LAYER_SCHEMA_VERSION
    source_files: List[str] = Field(default_factory=list)
    source_hash: str
    basics: Dict[str, Any] = Field(default_factory=dict)
    strategic_direction: str = ""
    target_roles: Dict[str, List[str]] = Field(default_factory=dict)
    target_geography: Dict[str, Any] = Field(default_factory=dict)
    strength_areas: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_highlights: List[Dict[str, str]] = Field(default_factory=list)
    work_entries: List[Dict[str, Any]] = Field(default_factory=list)
    project_entries: List[Dict[str, Any]] = Field(default_factory=list)
    education_entries: List[Dict[str, Any]] = Field(default_factory=list)
    certificates: List[Dict[str, Any]] = Field(default_factory=list)
    volunteer: List[Dict[str, Any]] = Field(default_factory=list)
    motivation_language: str = ""
    resume_master: ResumeMaster
    role_records: List[RoleRecord] = Field(default_factory=list)
    role_variants: List[RoleVariant] = Field(default_factory=list)
    project_records: List[ProjectRecord] = Field(default_factory=list)
    project_variants: List[ProjectVariant] = Field(default_factory=list)
    evidence_atoms: List[EvidenceAtom] = Field(default_factory=list)
    skill_atoms: List[SkillAtom] = Field(default_factory=list)
    content_library: ContentLibrary
    selection_rules: SelectionRules
    layout_profile: LayoutProfile
    narrative_profile: NarrativeProfile
    profile_snapshot: ProfileSnapshot
    targeting_profile: TargetingProfile
    triage_profile: TriageProfile
    authoring_profile: AuthoringProfile


def persist_profile_layer(path: Path, layer: ProfileLayerBundle) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(layer.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_persisted_profile_layer(path: Path) -> Optional[ProfileLayerBundle]:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return ProfileLayerBundle.model_validate(raw)
    except Exception:
        return None


def _compute_source_hash(
    profile_text: str,
    resume: Dict[str, Any],
    source_files: Optional[List[str]] = None,
) -> str:
    return sha256(
        json.dumps(
            {
                "profile_text": profile_text,
                "resume": resume,
                "source_files": source_files or [],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _build_source_provenance(
    *,
    object_kind: str,
    source_files: Optional[List[str]],
    source_hash: str,
    inputs: Optional[List[str]] = None,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "object_kind": object_kind,
        "adapter": PROFILE_LAYER_SCHEMA_VERSION,
        "source_hash": source_hash,
        "source_files": [str(path) for path in (source_files or []) if str(path).strip()],
        "inputs": [str(item) for item in (inputs or []) if str(item).strip()],
        "notes": [str(item) for item in (notes or []) if str(item).strip()],
    }


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _safe_load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_heading_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return value or "item"


def _compact_text(text: str, max_len: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value[:max_len]


def _infer_default_language(profile_text: str, resume: Dict[str, Any]) -> str:
    languages = resume.get("languages", []) if isinstance(resume.get("languages"), list) else []
    haystacks = [profile_text]
    for entry in languages:
        if not isinstance(entry, dict):
            continue
        haystacks.extend([str(entry.get("language") or ""), str(entry.get("fluency") or "")])
    joined = " ".join(part.lower() for part in haystacks if part)
    if any(token in joined for token in ["norsk", "norwegian", "bokmål", "bokmal"]):
        return "nb"
    if "english" in joined:
        return "en"
    return "nb"


def _locale_for_language(language: str) -> str:
    return {
        "nb": "nb-NO",
        "nn": "nn-NO",
        "en": "en-US",
    }.get((language or "").lower(), "nb-NO")


def _default_section_order() -> List[str]:
    return [
        "basics",
        "work",
        "projects",
        "skills",
        "education",
        "certificates",
        "languages",
        "volunteer",
        "interests",
        "references",
    ]


def _normalize_resume_section_name(value: Any) -> str:
    normalized = _normalize_heading_key(str(value or ""))
    aliases = {
        "basics": "basics",
        "summary": "basics",
        "work": "work",
        "experience": "work",
        "projects": "projects",
        "project": "projects",
        "skills": "skills",
        "education": "education",
        "certificates": "certificates",
        "certifications": "certificates",
        "languages": "languages",
        "volunteer": "volunteer",
        "interests": "interests",
        "references": "references",
    }
    return aliases.get(normalized, "")


def _extract_resume_source_traits(resume: Dict[str, Any]) -> Dict[str, Any]:
    metadata = resume.get("metadata") if isinstance(resume.get("metadata"), dict) else {}
    if not metadata:
        metadata = resume.get("meta") if isinstance(resume.get("meta"), dict) else {}
    layout = resume.get("layout") if isinstance(resume.get("layout"), dict) else {}
    sections = resume.get("sections")
    source_section_order: List[str] = []
    if isinstance(sections, list):
        for item in sections:
            if isinstance(item, str):
                section_name = _normalize_resume_section_name(item)
            elif isinstance(item, dict):
                section_name = _normalize_resume_section_name(
                    item.get("key") or item.get("id") or item.get("name") or item.get("section")
                )
            else:
                section_name = ""
            if section_name and section_name not in source_section_order:
                source_section_order.append(section_name)
    elif isinstance(sections, dict):
        for key in sections.keys():
            section_name = _normalize_resume_section_name(key)
            if section_name and section_name not in source_section_order:
                source_section_order.append(section_name)
    return {
        "source_type": "reactive-resume.v5" if metadata or layout or source_section_order else "json-resume",
        "meta_version": str(metadata.get("version") or metadata.get("schemaVersion") or ""),
        "layout": layout,
        "source_section_order": source_section_order,
        "metadata_keys": sorted(metadata.keys()),
        "layout_keys": sorted(layout.keys()),
    }


def _section_key_for_title(title: str) -> str:
    title = title or ""
    if title.startswith("## "):
        title = title[3:]
    elif title.startswith("### "):
        title = title[4:]
    return _normalize_heading_key(title)


def _parse_markdown_sections(text: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            if current:
                current["content"] = "\n".join(current["lines"]).strip()
                sections.append(current)
            current = {
                "level": len(match.group(1)),
                "title": match.group(2).strip(),
                "key": _normalize_heading_key(match.group(2)),
                "lines": [],
            }
            continue
        if current is not None:
            current["lines"].append(line)
    if current:
        current["content"] = "\n".join(current["lines"]).strip()
        sections.append(current)
    return sections


def _section_by_title(sections: List[Dict[str, Any]], title_fragment: str) -> Dict[str, Any]:
    key = _normalize_heading_key(title_fragment)
    for section in sections:
        if key and key in section.get("key", ""):
            return section
    return {}


def _section_bullets(sections: List[Dict[str, Any]], title_fragment: str) -> List[str]:
    content = str(_section_by_title(sections, title_fragment).get("content") or "")
    items: List[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _section_paragraphs(sections: List[Dict[str, Any]], title_fragment: str) -> List[str]:
    content = str(_section_by_title(sections, title_fragment).get("content") or "")
    parts = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    return [part for part in parts if not part.startswith("- ")]


def _extract_profile_basics(profile_text: str, resume: Dict[str, Any]) -> Dict[str, Any]:
    basics = resume.get("basics", {}) if isinstance(resume.get("basics"), dict) else {}
    snapshot: Dict[str, str] = {}
    for line in profile_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        payload = stripped[2:]
        if ":" not in payload:
            continue
        key, value = payload.split(":", 1)
        snapshot[_normalize_heading_key(key)] = value.strip()
    return {
        "name": str(basics.get("name") or ""),
        "label": str(basics.get("label") or ""),
        "email": str(basics.get("email") or ""),
        "phone": str(basics.get("phone") or ""),
        "url": str(basics.get("url") or ""),
        "summary": str(basics.get("summary") or ""),
        "base": snapshot.get("base", ""),
        "languages": snapshot.get("languages", ""),
        "level": snapshot.get("level", ""),
        "positioning": snapshot.get("positioning", ""),
        "cognitive": snapshot.get("cognitive", ""),
    }


def _extract_motivation_language(sections: List[Dict[str, Any]]) -> str:
    for section in sections:
        content = str(section.get("content") or "")
        for line in content.splitlines():
            if "Motivation language core" not in line:
                continue
            if ":" in line:
                return line.split(":", 1)[1].strip().strip('"')
    return ""


def _strength_areas_from_resume(resume: Dict[str, Any]) -> List[Dict[str, Any]]:
    strength_areas: List[Dict[str, Any]] = []
    for entry in resume.get("skills", []) if isinstance(resume.get("skills"), list) else []:
        if not isinstance(entry, dict):
            continue
        strength_areas.append(
            {
                "name": str(entry.get("name") or "").strip(),
                "keywords": [str(keyword).strip() for keyword in (entry.get("keywords") or []) if str(keyword).strip()],
            }
        )
    return strength_areas


def _build_evidence_and_roles(
    resume: Dict[str, Any],
    primary_roles: List[str],
    secondary_roles: List[str],
    motivation_language: str,
) -> tuple[List[RoleRecord], List[RoleVariant], List[EvidenceAtom], List[Dict[str, Any]]]:
    role_records: List[RoleRecord] = []
    role_variants: List[RoleVariant] = []
    evidence_atoms: List[EvidenceAtom] = []
    work_entries: List[Dict[str, Any]] = []
    all_target_tags = [*primary_roles, *secondary_roles]

    work_items = resume.get("work", []) if isinstance(resume.get("work"), list) else []
    for idx, item in enumerate(work_items):
        if not isinstance(item, dict):
            continue
        company = str(item.get("name") or item.get("company") or "").strip()
        position = str(item.get("position") or "").strip()
        start = str(item.get("startDate") or "").strip()
        end = str(item.get("endDate") or "present").strip()
        summary = _compact_text(item.get("summary") or "")
        location = _compact_text(item.get("location") or "")
        role_record_id = f"role:{_slug(company)}:{_slug(position)}:{_slug(start or str(idx))}"
        highlights = [str(h).strip() for h in (item.get("highlights") or []) if str(h).strip()]
        evidence_ids: List[str] = []
        for h_idx, highlight in enumerate(highlights):
            evidence_id = f"{role_record_id}:evidence:{h_idx + 1}"
            evidence_atoms.append(
                EvidenceAtom(
                    evidence_atom_id=evidence_id,
                    source_type="role",
                    source_id=role_record_id,
                    text=highlight,
                    tags=[tag for tag in [company, position] if tag],
                    seniority_signals=[position] if position else [],
                    strength_score=80 if h_idx < 2 else 65,
                )
            )
            evidence_ids.append(evidence_id)
        variant_id = f"{role_record_id}:variant:default"
        role_variants.append(
            RoleVariant(
                role_variant_id=variant_id,
                role_record_id=role_record_id,
                label="default",
                language="nb",
                target_tags=[tag for tag in all_target_tags if tag][:6],
                summary=summary or (highlights[0] if highlights else ""),
                preferred_evidence_atom_ids=evidence_ids[:4],
                tone_profile=motivation_language or "",
            )
        )
        role_records.append(
            RoleRecord(
                role_record_id=role_record_id,
                company=company,
                title=position,
                location=location,
                date_range=" - ".join(part for part in [start, end] if part),
                canonical_facts={
                    "company": company,
                    "title": position,
                    "summary": summary,
                    "start": start,
                    "end": end,
                },
                role_variant_ids=[variant_id],
                evidence_atom_ids=evidence_ids,
                tags=[tag for tag in [company, position] if tag],
            )
        )
        work_entries.append(
            {
                "company": company,
                "position": position,
                "start": start,
                "end": end,
                "summary": summary,
                "highlights": highlights,
            }
        )
    return role_records, role_variants, evidence_atoms, work_entries


def _build_projects(
    resume: Dict[str, Any],
    target_tags: List[str],
) -> tuple[List[ProjectRecord], List[ProjectVariant], List[EvidenceAtom], List[Dict[str, Any]]]:
    project_records: List[ProjectRecord] = []
    project_variants: List[ProjectVariant] = []
    evidence_atoms: List[EvidenceAtom] = []
    project_entries: List[Dict[str, Any]] = []

    projects = resume.get("projects", []) if isinstance(resume.get("projects"), list) else []
    for idx, item in enumerate(projects):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or f"project-{idx + 1}").strip()
        description = _compact_text(item.get("description") or "", max_len=260)
        project_record_id = f"project:{_slug(name)}:{idx + 1}"
        evidence_ids: List[str] = []
        if description:
            evidence_id = f"{project_record_id}:evidence:1"
            evidence_atoms.append(
                EvidenceAtom(
                    evidence_atom_id=evidence_id,
                    source_type="project",
                    source_id=project_record_id,
                    text=description,
                    tags=[name],
                    strength_score=70,
                )
            )
            evidence_ids.append(evidence_id)
        variant_id = f"{project_record_id}:variant:default"
        project_variants.append(
            ProjectVariant(
                project_variant_id=variant_id,
                project_record_id=project_record_id,
                label="default",
                language="nb",
                target_tags=[tag for tag in target_tags if tag][:6],
                summary=description,
                preferred_evidence_atom_ids=evidence_ids,
            )
        )
        project_records.append(
            ProjectRecord(
                project_record_id=project_record_id,
                name=name,
                canonical_facts={"name": name, "description": description},
                project_variant_ids=[variant_id],
                evidence_atom_ids=evidence_ids,
                tags=[name],
            )
        )
        project_entries.append({"name": name, "description": description})
    return project_records, project_variants, evidence_atoms, project_entries


def _build_skill_atoms(resume: Dict[str, Any]) -> List[SkillAtom]:
    skill_atoms: List[SkillAtom] = []
    skills = resume.get("skills", []) if isinstance(resume.get("skills"), list) else []
    for idx, item in enumerate(skills):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or f"skill-{idx + 1}").strip()
        keywords = [str(keyword).strip() for keyword in (item.get("keywords") or []) if str(keyword).strip()]
        skill_atoms.append(
            SkillAtom(
                skill_atom_id=f"skill:{_slug(name)}:{idx + 1}",
                name=name,
                aliases=keywords,
                category=str(item.get("level") or item.get("category") or "").strip(),
                strength=70 if keywords else 55,
            )
        )
    return skill_atoms


def _build_narrative_profile(
    basics: Dict[str, Any],
    strategic_direction: str,
    motivation_language: str,
    source_provenance: Dict[str, Any],
) -> NarrativeProfile:
    voice_traits = [trait for trait in [basics.get("positioning", ""), motivation_language] if trait]
    preferred_positioning = [part for part in [basics.get("label", ""), strategic_direction] if part]
    return NarrativeProfile(
        narrative_profile_id="narrative:default",
        voice_traits=voice_traits[:4],
        preferred_positioning=[_compact_text(part, max_len=180) for part in preferred_positioning if part][:4],
        language_preferences=str(basics.get("languages") or ""),
        operator_notes=_compact_text(strategic_direction, max_len=240),
        source_provenance=source_provenance,
    )


def _build_content_library(
    *,
    resume_master_id: str,
    role_variants: List[RoleVariant],
    project_variants: List[ProjectVariant],
    evidence_atoms: List[EvidenceAtom],
    skill_atoms: List[SkillAtom],
    role_records: List[RoleRecord],
    project_records: List[ProjectRecord],
    source_provenance: Dict[str, Any],
) -> ContentLibrary:
    section_inventory = {
        "work": [record.role_record_id for record in role_records],
        "projects": [record.project_record_id for record in project_records],
        "skills": [skill.skill_atom_id for skill in skill_atoms],
        "evidence": [atom.evidence_atom_id for atom in evidence_atoms],
    }
    return ContentLibrary(
        content_library_id="content_library:default",
        resume_master_id=resume_master_id,
        role_variant_ids=[variant.role_variant_id for variant in role_variants],
        project_variant_ids=[variant.project_variant_id for variant in project_variants],
        evidence_atom_ids=[atom.evidence_atom_id for atom in evidence_atoms],
        skill_atom_ids=[skill.skill_atom_id for skill in skill_atoms],
        section_inventory=section_inventory,
        source_provenance=source_provenance,
    )


def _build_selection_rules(
    *,
    resume_master_id: str,
    content_library: ContentLibrary,
    role_variants: List[RoleVariant],
    project_variants: List[ProjectVariant],
    skill_atoms: List[SkillAtom],
    evidence_atoms: List[EvidenceAtom],
    education_entries: List[Dict[str, Any]],
    certificates: List[Dict[str, Any]],
    volunteer: List[Dict[str, Any]],
    languages: List[Dict[str, Any]],
    resume: Dict[str, Any],
    resume_traits: Dict[str, Any],
    source_provenance: Dict[str, Any],
) -> SelectionRules:
    derived_section_order = [
        section
        for section in _default_section_order()
        if (
            section == "basics"
            or (section == "work" and bool(content_library.section_inventory.get("work")))
            or (section == "projects" and bool(content_library.section_inventory.get("projects")))
            or (section == "skills" and bool(content_library.section_inventory.get("skills")))
            or (section == "education" and bool(education_entries))
            or (section == "certificates" and bool(certificates))
            or (section == "languages" and bool(languages))
            or (section == "volunteer" and bool(volunteer))
            or (section == "interests" and bool(resume.get("interests")))
            or (section == "references" and bool(resume.get("references")))
        )
    ]
    preferred_section_order = [
        section
        for section in resume_traits.get("source_section_order", [])
        if section in derived_section_order
    ] + [
        section
        for section in derived_section_order
        if section not in set(resume_traits.get("source_section_order", []))
    ]
    section_visibility = {section: section in preferred_section_order for section in _default_section_order()}
    max_items_per_section = {
        "work": min(4, len(content_library.section_inventory.get("work", []))),
        "projects": min(4, len(content_library.section_inventory.get("projects", []))),
        "skills": min(8, len(content_library.section_inventory.get("skills", []))),
        "education": min(2, len(education_entries)),
        "certificates": min(4, len(certificates)),
        "languages": min(4, len(languages)),
        "volunteer": min(2, len(volunteer)),
    }
    return SelectionRules(
        selection_rules_id="selection_rules:default",
        resume_master_id=resume_master_id,
        default_role_variant_ids=[variant.role_variant_id for variant in role_variants[:4]],
        default_project_variant_ids=[variant.project_variant_id for variant in project_variants[:4]],
        featured_skill_atom_ids=[skill.skill_atom_id for skill in skill_atoms[:8]],
        evidence_priority_ids=[atom.evidence_atom_id for atom in evidence_atoms[:8]],
        preferred_section_order=preferred_section_order,
        section_visibility=section_visibility,
        max_items_per_section={key: value for key, value in max_items_per_section.items() if value > 0},
        source_provenance=source_provenance,
    )


def _build_layout_profile(
    *,
    resume_master_id: str,
    default_language: str,
    selection_rules: SelectionRules,
    resume: Dict[str, Any],
    resume_traits: Dict[str, Any],
    source_provenance: Dict[str, Any],
) -> LayoutProfile:
    preferred_order = [
        section
        for section in resume_traits.get("source_section_order", [])
        if selection_rules.section_visibility.get(section, False)
    ] + [
        section
        for section in selection_rules.preferred_section_order
        if selection_rules.section_visibility.get(section, False)
        and section not in set(resume_traits.get("source_section_order", []))
    ]
    visible_sections = [
        section
        for section in preferred_order
        if selection_rules.section_visibility.get(section, False)
    ]
    hidden_sections = [section for section in _default_section_order() if section not in visible_sections]
    layout_source = resume_traits.get("layout", {}) if isinstance(resume_traits.get("layout"), dict) else {}
    locale = _locale_for_language(default_language)
    return LayoutProfile(
        layout_profile_id="layout_profile:rr-default",
        resume_master_id=resume_master_id,
        engine="reactive-resume",
        template_key=str(layout_source.get("template") or layout_source.get("templateKey") or "rr-json-resume-baseline"),
        locale=str(layout_source.get("locale") or locale),
        section_order=visible_sections,
        visible_sections=visible_sections,
        hidden_sections=hidden_sections,
        item_limits=dict(selection_rules.max_items_per_section),
        page_settings={
            "paper_size": str(
                layout_source.get("paperSize")
                or (layout_source.get("page") or {}).get("format")
                or "A4"
            ),
            "locale": str(layout_source.get("locale") or locale),
            "line_height": str(layout_source.get("lineHeight") or "normal"),
        },
        rr_compat={
            "resume_schema": str(resume.get("$schema") or ""),
            "meta_version": str(resume_traits.get("meta_version") or ""),
            "source_type": str(resume_traits.get("source_type") or ""),
            "metadata_keys": list(resume_traits.get("metadata_keys", [])),
            "layout_keys": list(resume_traits.get("layout_keys", [])),
            "section_order": visible_sections,
            "section_visibility": dict(selection_rules.section_visibility),
        },
        source_provenance=source_provenance,
    )


def build_profile_layer(
    profile_text: str,
    resume: Dict[str, Any],
    *,
    source_files: Optional[List[str]] = None,
) -> ProfileLayerBundle:
    sections = _parse_markdown_sections(profile_text)
    source_hash = _compute_source_hash(profile_text, resume, source_files)
    basics = _extract_profile_basics(profile_text, resume)
    strategic_direction = "\n\n".join(_section_paragraphs(sections, "Strategic direction"))
    primary_roles = _section_bullets(sections, "Primary targets")
    secondary_roles = _section_bullets(sections, "Secondary targets")
    stepping_roles = _section_bullets(sections, "Stepping-stone roles")
    geography_locations = _section_bullets(sections, "Location (OK if any)")
    remote_policy = ""
    for line in str(_section_by_title(sections, "Location (OK if any)").get("content") or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("remote/hybrid:"):
            remote_policy = stripped.split(":", 1)[1].strip()
            break
    target_roles = {
        "primary": primary_roles,
        "secondary": secondary_roles,
        "stepping_stone": stepping_roles,
    }
    target_geography = {
        "base": basics.get("base", ""),
        "locations": geography_locations,
        "remote_policy": remote_policy,
    }
    motivation_language = _extract_motivation_language(sections)
    strength_areas = _strength_areas_from_resume(resume)
    default_language = _infer_default_language(profile_text, resume)
    resume_traits = _extract_resume_source_traits(resume)

    role_records, role_variants, role_evidence, work_entries = _build_evidence_and_roles(
        resume,
        primary_roles,
        secondary_roles,
        motivation_language,
    )
    project_records, project_variants, project_evidence, project_entries = _build_projects(
        resume,
        [*primary_roles, *secondary_roles, *stepping_roles],
    )
    evidence_atoms = [*role_evidence, *project_evidence]
    skill_atoms = _build_skill_atoms(resume)
    evidence_highlights = [
        {
            "employer": next((record.company for record in role_records if record.role_record_id == atom.source_id), ""),
            "role": next((record.title for record in role_records if record.role_record_id == atom.source_id), ""),
            "text": atom.text,
        }
        for atom in evidence_atoms[:10]
    ]
    resume_master_provenance = _build_source_provenance(
        object_kind="ResumeMaster",
        source_files=source_files,
        source_hash=source_hash,
        inputs=["profile_pack.md", "resume.json"],
        notes=["Derived from local profile pack and resume source."],
    )
    narrative_profile_provenance = _build_source_provenance(
        object_kind="NarrativeProfile",
        source_files=source_files,
        source_hash=source_hash,
        inputs=["Candidate snapshot", "Strategic direction", "Motivation language core"],
        notes=["Narrative profile remains a JobPipe-owned derived layer, not resume-edit truth."],
    )
    narrative_profile = _build_narrative_profile(
        basics,
        strategic_direction,
        motivation_language,
        narrative_profile_provenance,
    )

    resume_master = ResumeMaster(
        resume_master_id="resume_master:default",
        source_type=str(resume_traits.get("source_type") or "jobpipe.local"),
        source_ref="::".join(source_files or []),
        default_language=default_language,
        role_record_ids=[record.role_record_id for record in role_records],
        project_record_ids=[record.project_record_id for record in project_records],
        skill_atom_ids=[skill.skill_atom_id for skill in skill_atoms],
        narrative_profile_id=narrative_profile.narrative_profile_id,
        source_provenance=resume_master_provenance,
    )
    core_skills = [skill.name for skill in skill_atoms][:10]
    core_evidence_ids = [atom.evidence_atom_id for atom in evidence_atoms[:8]]
    profile_snapshot = ProfileSnapshot(
        profile_snapshot_id="profile_snapshot:default",
        resume_master_id=resume_master.resume_master_id,
        target_roles=[*primary_roles, *secondary_roles, *stepping_roles],
        domain_strengths=[area.get("name", "") for area in strength_areas if area.get("name")][:8],
        seniority_profile=str(basics.get("level") or basics.get("label") or ""),
        location_preferences=geography_locations,
        core_skills=core_skills,
        core_evidence_atom_ids=core_evidence_ids,
        constraints=[constraint for constraint in [basics.get("base", ""), remote_policy] if constraint],
        source_provenance=_build_source_provenance(
            object_kind="ProfileSnapshot",
            source_files=source_files,
            source_hash=source_hash,
            inputs=["ResumeMaster", "Target roles", "Geography rules", "Strength areas"],
        ),
    )
    targeting_profile = TargetingProfile(
        targeting_profile_id="targeting_profile:default",
        profile_snapshot_id=profile_snapshot.profile_snapshot_id,
        allowed_geos=geography_locations,
        target_title_patterns=[*primary_roles, *secondary_roles, *stepping_roles],
        preferred_domains=[area.get("name", "") for area in strength_areas if area.get("name")][:6],
        connector_policies={"suggested_leads_bypass_geo": True},
        source_provenance=_build_source_provenance(
            object_kind="TargetingProfile",
            source_files=source_files,
            source_hash=source_hash,
            inputs=["Target roles", "Location rules", "Connector policies"],
        ),
    )
    triage_profile = TriageProfile(
        triage_profile_id="triage_profile:default",
        profile_snapshot_id=profile_snapshot.profile_snapshot_id,
        role_summary=_compact_text(
            "Primary roles: "
            + ", ".join(primary_roles)
            + ". Secondary roles: "
            + ", ".join(secondary_roles)
            + "."
        ),
        advantageous_match_hypotheses=[
            _compact_text(strategic_direction, max_len=160)
        ] if strategic_direction else [],
        transferable_strengths=[skill for skill in core_skills[:6]],
        skill_clusters=core_skills[:8],
        must_not_miss_patterns=targeting_profile.target_title_patterns[:8],
        evidence_atoms_compact=[atom.text for atom in evidence_atoms[:6]],
        source_provenance=_build_source_provenance(
            object_kind="TriageProfile",
            source_files=source_files,
            source_hash=source_hash,
            inputs=["ProfileSnapshot", "Evidence atoms", "Strength areas"],
        ),
    )
    authoring_profile = AuthoringProfile(
        authoring_profile_id="authoring_profile:default",
        profile_snapshot_id=profile_snapshot.profile_snapshot_id,
        strongest_storylines=[
            text for text in [
                _compact_text(strategic_direction, max_len=180),
                *(atom.text for atom in evidence_atoms[:4]),
            ] if text
        ][:6],
        selected_evidence_atom_ids=core_evidence_ids[:6],
        work_history_refs=resume_master.role_record_ids,
        project_refs=resume_master.project_record_ids,
        value_prop_templates=[role for role in primary_roles[:4]],
        gap_handling_templates=[
            "Bruk eldre men relevante erfaringer presist når de best forklarer matchen."
        ],
        writing_constraints=[
            value
            for value in [
                _compact_text(motivation_language, max_len=180),
                "Foretrekk presis norsk fremfor generisk AI-språk.",
            ]
            if value
        ],
        source_provenance=_build_source_provenance(
            object_kind="AuthoringProfile",
            source_files=source_files,
            source_hash=source_hash,
            inputs=["NarrativeProfile", "Evidence atoms", "Role records", "Project records"],
        ),
    )
    content_library = _build_content_library(
        resume_master_id=resume_master.resume_master_id,
        role_variants=role_variants,
        project_variants=project_variants,
        evidence_atoms=evidence_atoms,
        skill_atoms=skill_atoms,
        role_records=role_records,
        project_records=project_records,
        source_provenance=_build_source_provenance(
            object_kind="ContentLibrary",
            source_files=source_files,
            source_hash=source_hash,
            inputs=["Role variants", "Project variants", "Evidence atoms", "Skill atoms"],
        ),
    )
    languages = resume.get("languages", []) if isinstance(resume.get("languages"), list) else []
    education_entries = resume.get("education", []) if isinstance(resume.get("education"), list) else []
    certificates = resume.get("certificates", []) if isinstance(resume.get("certificates"), list) else []
    volunteer = resume.get("volunteer", []) if isinstance(resume.get("volunteer"), list) else []
    selection_rules = _build_selection_rules(
        resume_master_id=resume_master.resume_master_id,
        content_library=content_library,
        role_variants=role_variants,
        project_variants=project_variants,
        skill_atoms=skill_atoms,
        evidence_atoms=evidence_atoms,
        education_entries=education_entries,
        certificates=certificates,
        volunteer=volunteer,
        languages=languages,
        resume=resume,
        resume_traits=resume_traits,
        source_provenance=_build_source_provenance(
            object_kind="SelectionRules",
            source_files=source_files,
            source_hash=source_hash,
            inputs=["ContentLibrary", "Section availability", "Default item limits"],
        ),
    )
    layout_profile = _build_layout_profile(
        resume_master_id=resume_master.resume_master_id,
        default_language=default_language,
        selection_rules=selection_rules,
        resume=resume,
        resume_traits=resume_traits,
        source_provenance=_build_source_provenance(
            object_kind="LayoutProfile",
            source_files=source_files,
            source_hash=source_hash,
            inputs=["SelectionRules", "Resume section order", "JSON Resume compatibility"],
            notes=["Stable RR-compatible presentation defaults until a richer RR master source is available."],
        ),
    )
    return ProfileLayerBundle(
        source_files=source_files or [],
        source_hash=source_hash,
        basics=basics,
        strategic_direction=strategic_direction,
        target_roles=target_roles,
        target_geography=target_geography,
        strength_areas=strength_areas,
        evidence_highlights=evidence_highlights,
        work_entries=work_entries,
        project_entries=project_entries,
        education_entries=resume.get("education", []) if isinstance(resume.get("education"), list) else [],
        certificates=resume.get("certificates", []) if isinstance(resume.get("certificates"), list) else [],
        volunteer=resume.get("volunteer", []) if isinstance(resume.get("volunteer"), list) else [],
        motivation_language=motivation_language,
        resume_master=resume_master,
        role_records=role_records,
        role_variants=role_variants,
        project_records=project_records,
        project_variants=project_variants,
        evidence_atoms=evidence_atoms,
        skill_atoms=skill_atoms,
        content_library=content_library,
        selection_rules=selection_rules,
        layout_profile=layout_profile,
        narrative_profile=narrative_profile,
        profile_snapshot=profile_snapshot,
        targeting_profile=targeting_profile,
        triage_profile=triage_profile,
        authoring_profile=authoring_profile,
    )


def load_profile_layer(profile_path: Path, resume_path: Path) -> ProfileLayerBundle:
    return build_profile_layer(
        _safe_read_text(profile_path),
        _safe_load_json(resume_path),
        source_files=[str(profile_path), str(resume_path)],
    )


def load_profile_layer_for_paths(paths: JobPipePaths) -> ProfileLayerBundle:
    resume_path = paths.resume_json_path if paths.resume_json_path.exists() else paths.resume_fixed_json_path
    return load_profile_layer(paths.profile_pack_path, resume_path)


def load_or_build_profile_layer_for_paths(
    paths: JobPipePaths,
    *,
    persist: bool = True,
) -> ProfileLayerBundle:
    resume_path = paths.resume_json_path if paths.resume_json_path.exists() else paths.resume_fixed_json_path
    profile_text = _safe_read_text(paths.profile_pack_path)
    resume_payload = _safe_load_json(resume_path)
    source_files = [str(paths.profile_pack_path), str(resume_path)]
    source_hash = _compute_source_hash(profile_text, resume_payload, source_files)

    persisted = load_persisted_profile_layer(paths.profile_layer_state_path)
    if persisted is not None and persisted.source_hash == source_hash:
        return persisted

    layer = build_profile_layer(profile_text, resume_payload, source_files=source_files)
    if persist:
        persist_profile_layer(paths.profile_layer_state_path, layer)
    return layer


def build_triage_profile_text(layer: ProfileLayerBundle, *, max_chars: int = 1600) -> str:
    parts = [
        "Target roles: " + ", ".join(layer.profile_snapshot.target_roles[:8]),
        "Role summary: " + layer.triage_profile.role_summary,
        "Transferable strengths: " + ", ".join(layer.triage_profile.transferable_strengths[:8]),
        "Skill clusters: " + ", ".join(layer.triage_profile.skill_clusters[:10]),
        "Evidence: " + " | ".join(layer.triage_profile.evidence_atoms_compact[:6]),
        "Constraints: " + ", ".join(layer.profile_snapshot.constraints[:4]),
    ]
    text = "\n".join(part for part in parts if part.strip())
    return text[:max_chars]


def build_triage_instruction_profile_summary(
    layer: ProfileLayerBundle,
    *,
    max_chars: int = 900,
) -> str:
    parts = [
        "Candidate snapshot: "
        + " | ".join(
            part
            for part in [
                str(layer.basics.get("label") or ""),
                str(layer.basics.get("positioning") or ""),
                str(layer.profile_snapshot.seniority_profile or ""),
            ]
            if part
        ),
        "Primary targets: " + ", ".join(layer.target_roles.get("primary", [])[:6]),
        "Secondary targets: " + ", ".join(layer.target_roles.get("secondary", [])[:6]),
        "Stepping-stone roles: " + ", ".join(layer.target_roles.get("stepping_stone", [])[:6]),
        "Allowed geography: " + ", ".join(layer.targeting_profile.allowed_geos[:6]),
        "Remote policy: " + str(layer.target_geography.get("remote_policy") or ""),
        "Role summary: " + layer.triage_profile.role_summary,
    ]
    text = "\n".join(part for part in parts if part.strip() and not part.endswith(": "))
    return text[:max_chars]


def build_authoring_context(layer: ProfileLayerBundle) -> Dict[str, Any]:
    selected_ids = set(layer.authoring_profile.selected_evidence_atom_ids)
    selected_evidence = [
        atom.model_dump()
        for atom in layer.evidence_atoms
        if atom.evidence_atom_id in selected_ids
    ] or [atom.model_dump() for atom in layer.evidence_atoms[:6]]

    relevant_role_records = [
        record.model_dump()
        for record in layer.role_records
        if record.role_record_id in set(layer.authoring_profile.work_history_refs)
    ] or [record.model_dump() for record in layer.role_records[:4]]

    relevant_project_records = [
        record.model_dump()
        for record in layer.project_records
        if record.project_record_id in set(layer.authoring_profile.project_refs)
    ] or [record.model_dump() for record in layer.project_records[:4]]

    relevant_role_variants = [
        variant.model_dump()
        for variant in layer.role_variants
        if variant.role_record_id in {record["role_record_id"] for record in relevant_role_records}
    ]
    relevant_project_variants = [
        variant.model_dump()
        for variant in layer.project_variants
        if variant.project_record_id in {record["project_record_id"] for record in relevant_project_records}
    ]

    return {
        "schema_version": PROFILE_LAYER_SCHEMA_VERSION,
        "profile_snapshot": layer.profile_snapshot.model_dump(),
        "authoring_profile": layer.authoring_profile.model_dump(),
        "resume_master": layer.resume_master.model_dump(),
        "content_library": layer.content_library.model_dump(),
        "selection_rules": layer.selection_rules.model_dump(),
        "layout_profile": layer.layout_profile.model_dump(),
        "narrative_profile": layer.narrative_profile.model_dump(),
        "role_records": relevant_role_records,
        "role_variants": relevant_role_variants,
        "project_records": relevant_project_records,
        "project_variants": relevant_project_variants,
        "selected_evidence_atoms": selected_evidence,
        "strength_areas": layer.strength_areas,
        "motivation_language": layer.motivation_language,
    }


def build_profile_match_context(layer: ProfileLayerBundle) -> Dict[str, Any]:
    return {
        "schema_version": PROFILE_LAYER_SCHEMA_VERSION,
        "profile_snapshot": layer.profile_snapshot.model_dump(),
        "triage_profile": layer.triage_profile.model_dump(),
        "targeting_profile": layer.targeting_profile.model_dump(),
        "narrative_profile": layer.narrative_profile.model_dump(),
        "resume_master": layer.resume_master.model_dump(),
        "strength_areas": layer.strength_areas,
        "selected_role_variants": [
            variant.model_dump()
            for variant in layer.role_variants[:6]
        ],
        "selected_project_variants": [
            variant.model_dump()
            for variant in layer.project_variants[:4]
        ],
        "evidence_atoms_compact": [
            atom.model_dump()
            for atom in layer.evidence_atoms[:8]
        ],
    }


def build_pivot_context(layer: ProfileLayerBundle) -> Dict[str, Any]:
    return {
        "schema_version": PROFILE_LAYER_SCHEMA_VERSION,
        "profile_snapshot": layer.profile_snapshot.model_dump(),
        "targeting_profile": layer.targeting_profile.model_dump(),
        "triage_profile": layer.triage_profile.model_dump(),
        "authoring_profile": layer.authoring_profile.model_dump(),
        "narrative_profile": layer.narrative_profile.model_dump(),
        "strongest_storylines": list(layer.authoring_profile.strongest_storylines[:6]),
        "transferable_strengths": list(layer.triage_profile.transferable_strengths[:6]),
    }


def build_reverse_triage_context(layer: ProfileLayerBundle) -> Dict[str, Any]:
    return {
        "schema_version": PROFILE_LAYER_SCHEMA_VERSION,
        "profile_snapshot": layer.profile_snapshot.model_dump(),
        "targeting_profile": layer.targeting_profile.model_dump(),
        "triage_profile": layer.triage_profile.model_dump(),
        "narrative_profile": layer.narrative_profile.model_dump(),
        "must_not_miss_patterns": list(layer.triage_profile.must_not_miss_patterns[:8]),
        "advantageous_match_hypotheses": list(layer.triage_profile.advantageous_match_hypotheses[:4]),
    }


def build_profile_dashboard_payload(
    profile_path: Path,
    resume_path: Path,
    profile_draft_path: Path,
    *,
    projection_path: Optional[Path] = None,
) -> Dict[str, Any]:
    builder_state = _safe_load_json(profile_draft_path)
    layer = load_profile_layer(profile_path, resume_path)
    if projection_path is not None:
        persist_profile_layer(projection_path, layer)
    return {
        "schema_version": PROFILE_LAYER_SCHEMA_VERSION,
        "source_files": layer.source_files,
        "builder_state_path": str(profile_draft_path),
        "builder_state": {str(k): str(v) for k, v in builder_state.items() if v is not None},
        "basics": layer.basics,
        "strategic_direction": layer.strategic_direction,
        "target_roles": layer.target_roles,
        "target_geography": layer.target_geography,
        "strength_areas": layer.strength_areas,
        "evidence_highlights": layer.evidence_highlights,
        "work": layer.work_entries,
        "projects": layer.project_entries,
        "education": layer.education_entries,
        "certificates": layer.certificates,
        "volunteer": layer.volunteer,
        "motivation_language": layer.motivation_language,
        "derived": {
            "source_hash": layer.source_hash,
            "resume_master": layer.resume_master.model_dump(),
            "content_library": layer.content_library.model_dump(),
            "selection_rules": layer.selection_rules.model_dump(),
            "layout_profile": layer.layout_profile.model_dump(),
            "profile_snapshot": layer.profile_snapshot.model_dump(),
            "targeting_profile": layer.targeting_profile.model_dump(),
            "triage_profile": layer.triage_profile.model_dump(),
            "authoring_profile": layer.authoring_profile.model_dump(),
            "counts": {
                "role_records": len(layer.role_records),
                "role_variants": len(layer.role_variants),
                "project_records": len(layer.project_records),
                "project_variants": len(layer.project_variants),
                "evidence_atoms": len(layer.evidence_atoms),
                "skill_atoms": len(layer.skill_atoms),
                "content_library_sections": len(layer.content_library.section_inventory),
            },
        },
    }
