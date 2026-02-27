#!/usr/bin/env python3
"""CivicProof End-to-End Demo Script.

Usage:
    python scripts/demo_e2e.py [--api-url URL] [--seed-vendor VENDOR_NAME]

Steps per sprint plan S7:
    1. POST /v1/cases with seed (vendor name or UEI)
    2. Poll GET /v1/cases/{id} until status != 'processing'
    3. GET /v1/cases/{id}/pack → download JSON
    4. Print: grounding_rate, claim_count, citation_count, sources_used, time_elapsed
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import httpx

DEFAULT_API_URL = "http://localhost:8080"
DEFAULT_SEED_VENDOR = "Acme Defense Solutions"
POLL_INTERVAL_SECONDS = 5
MAX_POLL_ATTEMPTS = 60  # 5 min max


def main() -> None:
    parser = argparse.ArgumentParser(description="CivicProof E2E demo")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API base URL")
    parser.add_argument("--seed-vendor", default=DEFAULT_SEED_VENDOR, help="Vendor name seed")
    parser.add_argument("--uei", default=None, help="Vendor UEI seed (alternative to name)")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    args = parser.parse_args()

    api = args.api_url.rstrip("/")

    # ── Step 0: Health check ──
    print(f"[1/4] Checking API health at {api}...")
    try:
        health = httpx.get(f"{api}/health", timeout=10)
        health.raise_for_status()
        print(f"  ✓ API healthy: {health.json()}")
    except Exception as exc:
        print(f"  ✗ API unreachable: {exc}")
        sys.exit(1)

    # ── Step 1: Create case ──
    seed_input = {"vendor_name": args.seed_vendor}
    if args.uei:
        seed_input = {"uei": args.uei}

    print(f"\n[2/4] Creating case with seed: {json.dumps(seed_input)}...")
    start_time = time.monotonic()

    create_resp = httpx.post(
        f"{api}/v1/cases",
        json={"title": f"Demo: {args.seed_vendor or args.uei}", "seed_input": seed_input},
        timeout=30,
    )
    create_resp.raise_for_status()
    case = create_resp.json()
    case_id = case["case_id"]
    print(f"  ✓ Case created: {case_id} (status: {case['status']})")

    # ── Step 2: Poll until complete ──
    print(
        f"\n[3/4] Polling case status (every {POLL_INTERVAL_SECONDS}s, "
        f"max {MAX_POLL_ATTEMPTS} attempts)..."
    )
    attempt = 0
    while attempt < MAX_POLL_ATTEMPTS:
        attempt += 1
        time.sleep(POLL_INTERVAL_SECONDS)

        poll_resp = httpx.get(f"{api}/v1/cases/{case_id}", timeout=10)
        poll_resp.raise_for_status()
        status = poll_resp.json()["status"]

        elapsed = time.monotonic() - start_time
        print(f"  [{attempt}/{MAX_POLL_ATTEMPTS}] status={status} elapsed={elapsed:.1f}s")

        if status in ("complete", "failed", "blocked"):
            break
    else:
        print(f"  ✗ Timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS}s")
        sys.exit(1)

    total_elapsed = time.monotonic() - start_time

    if status == "failed":
        print(f"\n  ✗ Case FAILED after {total_elapsed:.1f}s")
        sys.exit(1)

    if status == "blocked":
        print(f"\n  ⚠ Case BLOCKED by auditor after {total_elapsed:.1f}s")
        sys.exit(1)

    # ── Step 3: Download case pack ──
    print("\n[4/4] Downloading case pack...")
    pack_resp = httpx.get(f"{api}/v1/cases/{case_id}/pack", timeout=30)
    pack_resp.raise_for_status()
    pack = pack_resp.json()

    # ── Results ──
    claims = pack.get("claims", [])
    citations = pack.get("citations", [])
    audit_events = pack.get("audit_events", [])

    findings = [c for c in claims if c.get("claim_type") == "finding"]
    risk_signals = [c for c in claims if c.get("claim_type") == "risk_signal"]

    # Count unique sources from audit events
    sources_used = list({
        e.get("stage", "unknown")
        for e in audit_events
        if e.get("stage") not in ("intake", "")
    })

    cited_claims = sum(1 for c in claims if c.get("is_audited", False))
    grounding_rate = cited_claims / len(claims) if claims else 0.0

    print("\n" + "=" * 60)
    print("  CivicProof E2E Demo Results")
    print("=" * 60)
    print(f"  Case ID:          {case_id}")
    print(f"  Status:           {status}")
    print(f"  Time elapsed:     {total_elapsed:.1f}s")
    print(f"  Pack hash:        {pack.get('pack_hash', 'N/A')}")
    print(
        f"  Claims:           {len(claims)} "
        f"({len(findings)} findings, {len(risk_signals)} risk signals)"
    )
    print(f"  Citations:        {len(citations)}")
    print(f"  Grounding rate:   {grounding_rate:.2%}")
    print(f"  Pipeline stages:  {', '.join(sources_used) or 'N/A'}")
    print(f"  Audit events:     {len(audit_events)}")
    print("=" * 60)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(pack, f, indent=2, default=str)
        print(f"\n  → Pack saved to {args.output}")

    # Exit with failure if grounding rate below S7 target
    if grounding_rate < 0.90:
        print(f"\n  ⚠ Grounding rate {grounding_rate:.2%} is below S7 target (0.90)")


if __name__ == "__main__":
    main()
