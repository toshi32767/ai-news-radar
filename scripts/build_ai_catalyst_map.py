#!/usr/bin/env python3
"""Build investment-facing AI catalyst mappings from AI News Radar outputs."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse


DEFAULT_PROFILE = Path("configs/investment_domains/ai_catalyst.json")
DEFAULT_STORIES = Path("data/stories-merged.json")
DEFAULT_LATEST = Path("data/latest-24h.json")
DEFAULT_OUTPUT = Path("data/ai-catalyst-stories.json")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_record_url(raw_url: Any) -> str:
    """Normalize only hard-duplicate URL noise, not semantic URL identity."""
    url = str(raw_url or "").strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url.lower()
    if not parsed.scheme or not parsed.netloc:
        return url.lower()

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    tracking_prefixes = ("utm_",)
    tracking_keys = {
        "f",
        "fbclid",
        "from",
        "from_source",
        "fromsource",
        "hmsr",
        "ref",
        "ref_src",
        "spm",
    }
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in tracking_keys and not key.lower().startswith(tracking_prefixes)
    ]
    query = urlencode(query_pairs, doseq=True)
    path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", query, ""))


def normalized_hard_title(raw_title: Any) -> str:
    title = str(raw_title or "").strip().lower()
    if not title:
        return ""
    title = re.sub(r"https?://\S+", " ", title)
    title = re.sub(r"[\W_]+", " ", title, flags=re.UNICODE)
    return re.sub(r"\s+", " ", title).strip()


def aggregate_story_text(story: dict[str, Any]) -> str:
    parts: list[str] = [
        normalize_text(story.get("title")),
        normalize_text(story.get("source")),
        normalize_text(story.get("source_name")),
        " ".join(str(item) for item in story.get("source_names") or []),
    ]
    for key in ("items", "sources"):
        for item in story.get(key) or []:
            if isinstance(item, dict):
                parts.extend(
                    [
                        normalize_text(item.get("title")),
                        normalize_text(item.get("source")),
                        normalize_text(item.get("source_name")),
                    ]
                )
    primary = story.get("primary_item")
    if isinstance(primary, dict):
        parts.extend(
            [
                normalize_text(primary.get("title")),
                normalize_text(primary.get("source")),
                normalize_text(primary.get("source_name")),
            ]
        )
    return " ".join(part for part in parts if part)


def keyword_matches(text: str, keywords: list[str]) -> list[str]:
    text_l = text.lower()
    matches: list[str] = []
    for keyword in keywords:
        raw = str(keyword or "").strip()
        if not raw:
            continue
        raw_l = raw.lower()
        if re.search(r"[\u4e00-\u9fff]", raw_l):
            matched = raw_l in text_l
        else:
            pattern = re.escape(raw_l).replace(r"\ ", r"\s+")
            if re.match(r"[a-z0-9]", raw_l[0]):
                pattern = r"(?<![a-z0-9])" + pattern
            if re.match(r"[a-z0-9]", raw_l[-1]):
                pattern = pattern + r"(?![a-z0-9])"
            matched = bool(re.search(pattern, text_l))
        if matched:
            matches.append(raw)
    return sorted(set(matches), key=lambda value: value.lower())


def matched_tracks(story: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    text = aggregate_story_text(story)
    out: list[dict[str, Any]] = []
    for track in profile.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        matches = keyword_matches(text, [str(k) for k in track.get("keywords") or []])
        if not matches:
            continue
        out.append(
            {
                "id": track.get("id"),
                "label": track.get("label"),
                "matched_keywords": matches,
                "chain_nodes": list(track.get("chain_nodes") or []),
                "a_share_themes": list(track.get("a_share_themes") or []),
            }
        )
    return out


def unique_flatten(rows: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for value in row.get(key) or []:
            s = str(value or "").strip()
            if s and s not in seen:
                seen.add(s)
                values.append(s)
    return values


def unique_values(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def merge_track_rows(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for track in [*existing, *incoming]:
        if not isinstance(track, dict):
            continue
        track_id = str(track.get("id") or "").strip()
        if not track_id:
            continue
        if track_id not in by_id:
            by_id[track_id] = {
                "id": track_id,
                "label": track.get("label"),
                "matched_keywords": [],
                "chain_nodes": [],
                "a_share_themes": [],
            }
            order.append(track_id)
        row = by_id[track_id]
        row["label"] = row.get("label") or track.get("label")
        row["matched_keywords"] = unique_values([*row.get("matched_keywords", []), *list(track.get("matched_keywords") or [])])
        row["chain_nodes"] = unique_values([*row.get("chain_nodes", []), *list(track.get("chain_nodes") or [])])
        row["a_share_themes"] = unique_values([*row.get("a_share_themes", []), *list(track.get("a_share_themes") or [])])
    return [by_id[track_id] for track_id in order]


def source_identity(source: dict[str, Any]) -> str:
    url = canonical_record_url(source.get("url"))
    source_name = str(source.get("source_name") or source.get("site_id") or source.get("source") or "").strip().lower()
    if url:
        return f"url::{url}::source::{source_name}"
    title = normalized_hard_title(source.get("title"))
    if title:
        return f"title::{title}"
    return json.dumps(source, sort_keys=True, ensure_ascii=False)


def merge_source_rows(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in [*existing, *incoming]:
        if not isinstance(source, dict):
            continue
        key = source_identity(source)
        if key in seen:
            continue
        seen.add(key)
        out.append(source)
    return out


def latest_time(values: list[Any]) -> Any:
    clean = [str(value) for value in values if value]
    return max(clean) if clean else None


def earliest_time(values: list[Any]) -> Any:
    clean = [str(value) for value in values if value]
    return min(clean) if clean else None


def evidence_rank(level: Any) -> int:
    ranks = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
    return ranks.get(str(level or "").upper(), 0)


def merge_duplicate_record(primary: dict[str, Any], duplicate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    merged["duplicate_count"] = int(merged.get("duplicate_count") or 1) + int(duplicate.get("duplicate_count") or 1)
    merged["duplicate_story_ids"] = unique_values(
        [
            *(merged.get("duplicate_story_ids") or [merged.get("story_id")]),
            *(duplicate.get("duplicate_story_ids") or [duplicate.get("story_id")]),
        ]
    )
    merged["latest_at"] = latest_time([merged.get("latest_at"), duplicate.get("latest_at")])
    merged["earliest_at"] = earliest_time([merged.get("earliest_at"), duplicate.get("earliest_at")])
    merged["investment_score"] = max(float(merged.get("investment_score") or 0), float(duplicate.get("investment_score") or 0))
    merged["ai_story_score"] = max(float(merged.get("ai_story_score") or 0), float(duplicate.get("ai_story_score") or 0))
    if evidence_rank(duplicate.get("evidence_level")) > evidence_rank(merged.get("evidence_level")):
        merged["evidence_level"] = duplicate.get("evidence_level")

    merged["tracks"] = merge_track_rows(list(merged.get("tracks") or []), list(duplicate.get("tracks") or []))
    merged["chain_nodes"] = unique_flatten(list(merged.get("tracks") or []), "chain_nodes")
    merged["a_share_themes"] = unique_flatten(list(merged.get("tracks") or []), "a_share_themes")
    merged["validation_needed"] = unique_values([*list(merged.get("validation_needed") or []), *list(duplicate.get("validation_needed") or [])])
    merged["reasons"] = unique_values([*list(merged.get("reasons") or []), *list(duplicate.get("reasons") or [])])
    merged["sources"] = merge_source_rows(list(merged.get("sources") or []), list(duplicate.get("sources") or []))
    merged["source_count"] = max(int(merged.get("source_count") or 1), len(merged["sources"]) or 1)
    return merged


def record_hard_dedupe_keys(record: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    url = canonical_record_url(record.get("url"))
    if url:
        keys.append(f"url::{url}")
    title = normalized_hard_title(record.get("title"))
    if title:
        keys.append(f"title::{title}")
    return keys


def dedupe_hard_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out: list[dict[str, Any]] = []
    key_to_index: dict[str, int] = {}
    duplicate_groups = 0
    duplicate_records = 0

    for record in records:
        record = dict(record)
        record["duplicate_count"] = int(record.get("duplicate_count") or 1)
        record["duplicate_story_ids"] = unique_values(record.get("duplicate_story_ids") or [record.get("story_id")])
        keys = record_hard_dedupe_keys(record)
        match_index = next((key_to_index[key] for key in keys if key in key_to_index), None)
        if match_index is None:
            out.append(record)
            index = len(out) - 1
            for key in keys:
                key_to_index[key] = index
            continue

        before_count = int(out[match_index].get("duplicate_count") or 1)
        out[match_index] = merge_duplicate_record(out[match_index], record)
        after_count = int(out[match_index].get("duplicate_count") or 1)
        if before_count == 1 and after_count > 1:
            duplicate_groups += 1
        duplicate_records += int(record.get("duplicate_count") or 1)
        for key in [*record_hard_dedupe_keys(out[match_index]), *keys]:
            key_to_index[key] = match_index

    return out, {
        "strategy": "canonical_url_or_exact_normalized_title_v1",
        "raw_records": len(records),
        "deduped_records": len(out),
        "duplicate_groups": duplicate_groups,
        "duplicate_records": duplicate_records,
    }


def evidence_level_for(story: dict[str, Any], profile: dict[str, Any]) -> str:
    reasons = {str(reason) for reason in story.get("reasons") or []}
    category = str(story.get("category") or "")
    source_name = str(story.get("source_name") or "")
    if "official_source" in reasons or category == "official" or source_name == "Official AI Updates":
        return "L1"
    return str(profile.get("default_evidence_level") or "L0")


def story_score(story: dict[str, Any]) -> float:
    for key in ("score", "importance_score", "importance"):
        try:
            return max(0.0, min(1.0, float(story.get(key))))
        except (TypeError, ValueError):
            continue
    return 0.0


def investment_score(story: dict[str, Any], tracks: list[dict[str, Any]]) -> float:
    base = story_score(story)
    source_count = max(1, int(story.get("source_count") or story.get("item_count") or 1))
    heat = min(1.0, (source_count - 1) / 4)
    track_strength = min(1.0, len(tracks) / 3)
    keyword_strength = min(
        1.0,
        sum(len(track.get("matched_keywords") or []) for track in tracks) / 8,
    )
    score = (base * 0.35) + (track_strength * 0.3) + (keyword_strength * 0.2) + (heat * 0.15)
    return round(max(0.0, min(1.0, score)), 4)


def catalyst_record(story: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any] | None:
    tracks = matched_tracks(story, profile)
    if not tracks:
        return None
    return {
        "story_id": story.get("story_id") or story.get("id"),
        "title": story.get("title"),
        "url": story.get("primary_url") or story.get("url"),
        "source": story.get("source"),
        "source_name": story.get("source_name"),
        "source_count": story.get("source_count") or story.get("item_count") or 1,
        "latest_at": story.get("latest_at") or story.get("published_at") or story.get("first_seen_at"),
        "earliest_at": story.get("earliest_at") or story.get("published_at"),
        "ai_story_score": story_score(story),
        "investment_score": investment_score(story, tracks),
        "investment_domain": profile.get("domain") or "ai_catalyst",
        "investment_role": profile.get("investment_role") or "demand_side_catalyst",
        "evidence_level": evidence_level_for(story, profile),
        "tracks": tracks,
        "chain_nodes": unique_flatten(tracks, "chain_nodes"),
        "a_share_themes": unique_flatten(tracks, "a_share_themes"),
        "validation_needed": list(profile.get("validation_needed") or []),
        "reasons": list(story.get("reasons") or []),
        "sources": list(story.get("sources") or story.get("items") or []),
    }


def item_to_story(item: dict[str, Any]) -> dict[str, Any]:
    item_id = item.get("id")
    title = item.get("title_bilingual") or item.get("title")
    return {
        "story_id": f"item_{item_id}" if item_id else None,
        "title": title,
        "url": item.get("url"),
        "primary_url": item.get("url"),
        "source": item.get("source"),
        "source_name": item.get("site_name"),
        "source_count": 1,
        "latest_at": item.get("published_at") or item.get("first_seen_at"),
        "earliest_at": item.get("published_at") or item.get("first_seen_at"),
        "score": item.get("ai_score"),
        "category": item.get("ai_label"),
        "reasons": [item.get("ai_relevance_reason")] if item.get("ai_relevance_reason") else [],
        "sources": [
            {
                "id": item.get("id"),
                "title": title,
                "url": item.get("url"),
                "source": item.get("source"),
                "source_name": item.get("site_name"),
                "site_id": item.get("site_id"),
                "published_at": item.get("published_at"),
            }
        ],
    }


def load_stories(stories_payload: dict[str, Any], latest_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    stories = stories_payload.get("stories")
    if isinstance(stories, list) and stories:
        return [item for item in stories if isinstance(item, dict)], "stories-merged"
    items = latest_payload.get("items")
    if isinstance(items, list):
        return [item_to_story(item) for item in items if isinstance(item, dict)], "latest-24h"
    return [], "empty"


def build_payload(
    *,
    profile: dict[str, Any],
    stories_payload: dict[str, Any],
    latest_payload: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    stories, input_kind = load_stories(stories_payload, latest_payload)
    records = [record for story in stories if (record := catalyst_record(story, profile))]
    records.sort(
        key=lambda item: (
            -float(item.get("investment_score") or 0),
            str(item.get("latest_at") or ""),
            str(item.get("title") or ""),
        )
    )
    raw_record_count = len(records)
    records, dedupe_stats = dedupe_hard_records(records)
    records.sort(
        key=lambda item: (
            -float(item.get("investment_score") or 0),
            str(item.get("latest_at") or ""),
            str(item.get("title") or ""),
        )
    )
    track_counts: dict[str, int] = {}
    for record in records:
        for track in record.get("tracks") or []:
            track_id = str(track.get("id") or "")
            if track_id:
                track_counts[track_id] = track_counts.get(track_id, 0) + 1
    return {
        "generated_at": generated_at or utc_now_iso(),
        "source_generated_at": stories_payload.get("generated_at") or latest_payload.get("generated_at"),
        "input_kind": input_kind,
        "domain": profile.get("domain") or "ai_catalyst",
        "display_name": profile.get("display_name") or "AI Catalyst",
        "total_input_stories": len(stories),
        "total_catalyst_stories": len(records),
        "total_raw_catalyst_stories": raw_record_count,
        "dedupe": dedupe_stats,
        "track_counts": dict(sorted(track_counts.items())),
        "items": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AI catalyst investment mapping from AI News Radar JSON")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE), help="Investment domain profile JSON")
    parser.add_argument("--stories", default=str(DEFAULT_STORIES), help="stories-merged.json path")
    parser.add_argument("--latest", default=str(DEFAULT_LATEST), help="latest-24h.json path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    args = parser.parse_args()

    profile_path = Path(args.profile)
    stories_path = Path(args.stories)
    latest_path = Path(args.latest)
    output_path = Path(args.output)

    profile = read_json(profile_path)
    if not profile:
        raise SystemExit(f"Profile not found or invalid: {profile_path}")

    payload = build_payload(
        profile=profile,
        stories_payload=read_json(stories_path),
        latest_payload=read_json(latest_path),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {output_path} with {payload['total_catalyst_stories']} catalyst stories "
        f"from {payload['total_input_stories']} {payload['input_kind']} records."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
