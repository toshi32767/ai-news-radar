#!/usr/bin/env python3
"""Build investment-facing AI catalyst mappings from AI News Radar outputs."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
