#!/usr/bin/env python3
"""Run OpenAPI discovery for e-Procurement SEA and LOC APIs and write cache."""
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if present (before any imports that need env vars)
from app.utils.env import load_env_if_present
load_env_if_present()


def main() -> int:
    import argparse
    from connectors.eprocurement.openapi_discovery import (
        DEFAULT_LOC_SWAGGER_URL,
        DEFAULT_SEA_SWAGGER_URL,
        discover_cpv_label_endpoint,
        discover_publication_detail_endpoint,
        discover_search_publications_endpoint,
        download_swagger,
        is_shortlink_candidate,
        iter_operations,
        load_or_discover_endpoints,
    )

    parser = argparse.ArgumentParser(
        description="Discover e-Procurement endpoints from Swagger/OpenAPI and write cache."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force discovery and overwrite cache file",
    )
    args = parser.parse_args()

    try:
        endpoints = load_or_discover_endpoints(
            force=args.force,
            sea_swagger_url=DEFAULT_SEA_SWAGGER_URL,
            loc_swagger_url=DEFAULT_LOC_SWAGGER_URL,
        )
    except Exception as e:
        print(f"Discovery failed: {e}", file=sys.stderr)
        return 1

    # Print selected endpoints (from cache)
    print("\n--- Selected search_publications ---")
    sp = endpoints.search_publications
    print(
        f"  {sp.get('method', 'POST')} {sp.get('path', '')} "
        f"(style={sp.get('style')}, term_param={sp.get('term_param')}, "
        f"page_param={sp.get('page_param')}, page_size_param={sp.get('page_size_param')})"
    )
    print("\n--- Selected cpv_label ---")
    cpv = endpoints.cpv_label
    print(
        f"  {cpv.get('method', 'GET')} {cpv.get('path', '')} "
        f"(code_param={cpv.get('code_param')}, lang_param={cpv.get('lang_param')})"
    )
    pd = endpoints.publication_detail
    if pd:
        print("\n--- Selected publication_detail ---")
        print(f"  {pd.get('method', 'GET')} {pd.get('path', '')} (id_param={pd.get('id_param')})")
    else:
        print("\n--- publication_detail: (none discovered) ---")

    # Re-fetch candidates to show reasoning (winner path, score, top 3 reasons)
    try:
        sea_spec = download_swagger(DEFAULT_SEA_SWAGGER_URL)
        loc_spec = download_swagger(DEFAULT_LOC_SWAGGER_URL)
        # Show candidates excluded due to shortlink
        excluded_shortlink = [
            (m, p) for m, p, op in iter_operations(sea_spec)
            if is_shortlink_candidate(p, op.get("summary") or "")
        ]
        if excluded_shortlink:
            print("\n--- Excluded (shortlink) ---")
            for method, path in excluded_shortlink:
                print(f"  {method} {path}")
        search_candidates = discover_search_publications_endpoint(sea_spec)
        cpv_candidates = discover_cpv_label_endpoint(loc_spec)
        detail_candidates = discover_publication_detail_endpoint(sea_spec)

        if search_candidates:
            winner = search_candidates[0]
            print("\n--- Reasoning: search_publications winner ---")
            print(f"  Winner: {winner.method} {winner.path}")
            print(f"  Score: {winner.score:.1f}")
            reasons = winner.score_reasons[:3]
            if reasons:
                print("  Top 3 reasons:")
                for r in reasons:
                    print(f"    - {r}")
            else:
                print("  (no reason details)")

        print("\n--- Top 5 candidates for search_publications ---")
        for i, c in enumerate(search_candidates[:5], 1):
            print(
                f"  {i}. {c.method} {c.path} (score={c.score:.1f}) "
                f"term={c.term_param} page={c.page_param} pageSize={c.page_size_param} style={c.style}"
            )
        print("\n--- Top 5 candidates for cpv_label ---")
        for i, c in enumerate(cpv_candidates[:5], 1):
            print(
                f"  {i}. {c.method} {c.path} (score={c.score}) "
                f"code_param={c.code_param} lang_param={c.lang_param}"
            )
        if detail_candidates:
            print("\n--- Top 3 candidates for publication_detail ---")
            for i, c in enumerate(detail_candidates[:3], 1):
                print(f"  {i}. {c.method} {c.path} (score={c.score}) path_params={c.path_params}")
    except Exception as e:
        print(f"\n(Could not re-fetch candidates for display: {e})")

    print(f"\nCache written. updated_at={endpoints.updated_at}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ModuleNotFoundError as e:
        print(f"Missing module: {e}", file=sys.stderr)
        print("Run the environment bootstrap, then try again:", file=sys.stderr)
        print("  python scripts/bootstrap_env.py", file=sys.stderr)
        sys.exit(1)
