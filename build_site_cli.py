"""Command line for the phone site: scan (or reuse a saved scan), check it is complete,
and write the site folder. Used by the scheduled GitHub workflow.

    python build_site_cli.py --out site
    python build_site_cli.py --out site --from-cache _cache/scan_result.pkl   (testing)
"""
import argparse
import pickle
import sys

import scan_runner
import site_builder
from scanners import stocks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    ap.add_argument("--repo-url", default=site_builder.DEFAULT_REPO_URL)
    ap.add_argument("--from-cache", help="reuse a pickled scan instead of scanning (testing)")
    ap.add_argument("--no-free", action="store_true", help="skip the free-version lookups")
    ap.add_argument("--force", action="store_true", help="publish even if the quality check fails")
    args = ap.parse_args()

    if args.from_cache:
        with open(args.from_cache, "rb") as f:
            result = pickle.load(f)
    else:
        result = scan_runner.run_full_scan(progress_cb=lambda m: print(m, flush=True), tech_split=0.6)

    problems = site_builder.check_quality(result, len(stocks.load_universe()))
    if problems:
        print("QUALITY CHECK FAILED: " + "; ".join(problems), flush=True)
        if not args.force:
            print("Not publishing: the last good snapshot stays up.", flush=True)
            return 1

    info = site_builder.build_site(result, args.out, repo_url=args.repo_url,
                                   look_up_free_versions=not args.no_free,
                                   progress=lambda m: print(m, flush=True))
    print(f"Built phone site {info['build_id']} (scanned {info['scan_label']}); "
          f"{info['free_stories']} stories pre-searched; sizes: {info['sizes']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
