from __future__ import annotations

from scripts.build_ai_catalyst_map import build_payload
from scripts.build_ai_catalyst_map import catalyst_record
from scripts.build_ai_catalyst_map import item_to_story


PROFILE = {
    "domain": "ai_catalyst",
    "display_name": "AI产业催化",
    "default_evidence_level": "L0",
    "investment_role": "demand_side_catalyst",
    "validation_needed": ["需要验证"],
    "tracks": [
        {
            "id": "compute",
            "label": "算力基础设施",
            "keywords": ["nvidia", "gpu", "算力"],
            "chain_nodes": ["GPU", "AI服务器"],
            "a_share_themes": ["算力"],
        },
        {
            "id": "optical",
            "label": "光通信与高速互联",
            "keywords": ["光模块", "cpo", "800g"],
            "chain_nodes": ["光模块", "CPO"],
            "a_share_themes": ["CPO", "光模块"],
        },
    ],
}


def test_catalyst_record_maps_compute_and_optical_tracks():
    story = {
        "story_id": "story-1",
        "title": "NVIDIA GPU cluster drives 800G 光模块 and CPO demand",
        "url": "https://example.com/story",
        "source": "Example",
        "source_name": "AI HOT",
        "source_count": 3,
        "score": 0.8,
        "reasons": ["multi_source"],
    }

    record = catalyst_record(story, PROFILE)

    assert record is not None
    assert record["investment_domain"] == "ai_catalyst"
    assert record["investment_role"] == "demand_side_catalyst"
    assert record["evidence_level"] == "L0"
    assert record["investment_score"] > 0.5
    assert {track["id"] for track in record["tracks"]} == {"compute", "optical"}
    assert "GPU" in record["chain_nodes"]
    assert "光模块" in record["chain_nodes"]
    assert "CPO" in record["a_share_themes"]


def test_official_story_maps_to_l1_evidence():
    story = {
        "story_id": "story-2",
        "title": "OpenAI announces new inference data center GPU plans",
        "url": "https://example.com/official",
        "source": "OpenAI News",
        "source_name": "Official AI Updates",
        "source_count": 1,
        "score": 0.9,
        "category": "official",
        "reasons": ["official_source"],
    }

    record = catalyst_record(story, PROFILE)

    assert record is not None
    assert record["evidence_level"] == "L1"


def test_build_payload_falls_back_to_latest_items():
    latest_item = {
        "id": "item-1",
        "site_id": "tophub",
        "site_name": "TopHub",
        "source": "人工智能",
        "title": "NVIDIA GPU 算力需求升温",
        "url": "https://example.com/item",
        "first_seen_at": "2026-06-10T00:00:00Z",
        "ai_score": 0.7,
        "ai_label": "infra_compute",
        "ai_relevance_reason": "matched_ai_signal",
    }

    payload = build_payload(
        profile=PROFILE,
        stories_payload={},
        latest_payload={"generated_at": "2026-06-10T00:00:00Z", "items": [latest_item]},
        generated_at="2026-06-10T01:00:00Z",
    )

    assert payload["generated_at"] == "2026-06-10T01:00:00Z"
    assert payload["source_generated_at"] == "2026-06-10T00:00:00Z"
    assert payload["input_kind"] == "latest-24h"
    assert payload["total_input_stories"] == 1
    assert payload["total_catalyst_stories"] == 1
    assert payload["track_counts"] == {"compute": 1}
    assert payload["items"][0]["title"] == item_to_story(latest_item)["title"]


def test_build_payload_merges_hard_duplicate_catalyst_records():
    stories_payload = {
        "generated_at": "2026-06-10T00:00:00Z",
        "stories": [
            {
                "story_id": "story-a",
                "title": "林洋能源在雄安成立算力技术公司，注册资本2亿",
                "url": "https://www.36kr.com/newsflashes/3846750053403137",
                "source_name": "NewsNow",
                "source_count": 1,
                "score": 0.7,
                "sources": [
                    {
                        "title": "林洋能源在雄安成立算力技术公司，注册资本2亿",
                        "url": "https://www.36kr.com/newsflashes/3846750053403137",
                        "source_name": "NewsNow",
                    }
                ],
            },
            {
                "story_id": "story-b",
                "title": "林洋能源在雄安成立算力技术公司，注册资本2亿",
                "url": "https://36kr.com/newsflashes/3846750053403137?f=rss",
                "source_name": "Info Flow",
                "source_count": 1,
                "score": 0.6,
                "sources": [
                    {
                        "title": "林洋能源在雄安成立算力技术公司，注册资本2亿",
                        "url": "https://36kr.com/newsflashes/3846750053403137?f=rss",
                        "source_name": "Info Flow",
                    }
                ],
            },
        ],
    }

    payload = build_payload(
        profile=PROFILE,
        stories_payload=stories_payload,
        latest_payload={},
        generated_at="2026-06-10T01:00:00Z",
    )

    assert payload["total_raw_catalyst_stories"] == 2
    assert payload["total_catalyst_stories"] == 1
    assert payload["dedupe"]["duplicate_groups"] == 1
    assert payload["dedupe"]["duplicate_records"] == 1

    record = payload["items"][0]
    assert record["duplicate_count"] == 2
    assert record["duplicate_story_ids"] == ["story-a", "story-b"]
    assert record["source_count"] == 2
    assert len(record["sources"]) == 2
    assert record["investment_score"] >= 0.3
    assert {track["id"] for track in record["tracks"]} == {"compute"}
