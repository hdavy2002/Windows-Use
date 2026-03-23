"""
humphi_search/main.py

Entry point for Humphi file search system.

Run modes:
    python main.py scan          — scan default folders and index files
    python main.py scan --watch  — scan then keep watching for new files
    python main.py search        — interactive search mode
    python main.py stats         — show index statistics
"""

import sys
import time
import argparse
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("humphi")

# Default folders to scan — Windows paths
DEFAULT_FOLDERS = [
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Pictures",
]


def onboarding() -> list[Path]:
    """
    Ask user which folders to scan.
    Returns list of confirmed folders.
    """
    print("\n" + "="*55)
    print("  HUMPHI AI — File Search Setup")
    print("="*55)
    print("\nHumphi will scan your files so you can find them")
    print("using plain English. e.g. 'find that invoice for Sharma'")
    print("\nAll processing happens locally on your machine.")
    print("File contents never leave your computer.\n")

    confirmed = []
    for folder in DEFAULT_FOLDERS:
        if folder.exists():
            ans = input(f"  Scan {folder.name}? ({folder}) [Y/n]: ").strip().lower()
            if ans != "n":
                confirmed.append(folder)

    # Allow custom folder
    custom = input("\n  Add another folder? (press Enter to skip): ").strip()
    if custom:
        custom_path = Path(custom)
        if custom_path.exists():
            confirmed.append(custom_path)
        else:
            print(f"  Folder not found: {custom}")

    return confirmed


def cmd_scan(args):
    """Scan folders and index all files."""
    from humphi_search.indexer import HumphiIndexer
    from humphi_search.cloud_backup import HumphiCloudBackup

    # Onboarding or use defaults
    if args.folders:
        folders = [Path(f) for f in args.folders]
    else:
        folders = onboarding()

    if not folders:
        print("No folders selected. Exiting.")
        return

    print(f"\nStarting indexer...")
    indexer = HumphiIndexer()
    cloud = HumphiCloudBackup()

    if cloud.is_enabled():
        print("Cloud backup: ENABLED")
    else:
        print("Cloud backup: disabled (local only)")

    print()

    # Progress display
    def progress(current, total, filename):
        pct = int((current / total) * 100)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct}% — {filename[:40]:<40}", end="", flush=True)
        if current == total:
            print()

    start = time.time()

    for folder in folders:
        indexer.scan_folder(folder, progress_callback=progress)

    elapsed = round(time.time() - start, 1)
    stats = indexer.stats()

    print(f"\n{'='*55}")
    print(f"  Scan complete in {elapsed}s")
    print(f"  Total in index: {stats['total_indexed']:,} files")
    print(f"  New this session: {stats['session_indexed']:,}")
    print(f"  Already up to date: {stats['session_skipped']:,}")
    if stats['session_errors']:
        print(f"  Errors: {stats['session_errors']}")
    print(f"{'='*55}\n")

    # Start watcher if requested
    if args.watch:
        from humphi_search.watcher import HumphiWatcher
        print("Watching for new files... (Ctrl+C to stop)\n")
        watcher = HumphiWatcher(folders, indexer)
        watcher.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            watcher.stop()
            print("\nWatcher stopped.")


def cmd_search(args):
    """Interactive natural language file search."""
    from humphi_search.search import HumphiSearch

    searcher = HumphiSearch()
    count = searcher.count()

    print(f"\n{'='*55}")
    print(f"  HUMPHI FILE SEARCH")
    print(f"  {count:,} files indexed")
    print(f"{'='*55}")
    print("  Type a description to find files.")
    print("  Examples:")
    print("    invoice sharma")
    print("    photos from birthday")
    print("    excel budget 2025")
    print("    pdf contract")
    print("  Type 'quit' to exit.\n")

    if count == 0:
        print("  No files indexed yet. Run: python main.py scan\n")
        return

    while True:
        try:
            query = input("Search > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            break

        # Optional filters
        file_type = None
        extension = None
        if query.startswith("image:"):
            file_type = "image"
            query = query[6:].strip()
        elif query.startswith("doc:"):
            file_type = "document"
            query = query[4:].strip()
        elif query.startswith("."):
            parts = query.split(" ", 1)
            extension = parts[0]
            query = parts[1] if len(parts) > 1 else query

        start = time.time()
        results = searcher.search(query, n_results=8, file_type=file_type, extension=extension)
        elapsed = round((time.time() - start) * 1000, 1)

        if not results:
            print(f"  No results found. ({elapsed}ms)\n")
            continue

        print(f"\n  Found {len(results)} results ({elapsed}ms):\n")
        for i, r in enumerate(results, 1):
            score_bar = "█" * int(r["score"] / 10)
            print(f"  {i}. [{score_bar:<10}] {r['score']}%  {r['filename']}")
            print(f"     📁 {r['folder']}")
            print(f"     🕒 {r['modified'][:10]}  📦 {r['size_bytes'] // 1024}KB")
            print()


def cmd_stats(args):
    """Show index statistics."""
    from humphi_search.search import HumphiSearch
    import chromadb

    searcher = HumphiSearch()
    total = searcher.count()

    print(f"\n{'='*55}")
    print(f"  HUMPHI FILE INDEX STATS")
    print(f"{'='*55}")
    print(f"  Total files indexed: {total:,}")

    if total > 0:
        # Get breakdown by type
        try:
            docs = searcher.search("document", n_results=1, file_type="document")
            images = searcher.search("image", n_results=1, file_type="image")
            print(f"  DB location: {Path.home() / '.humphi' / 'vectordb'}")
        except Exception:
            pass

    print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Humphi AI File Search")
    subparsers = parser.add_subparsers(dest="command")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan and index files")
    scan_parser.add_argument("--folders", nargs="*", help="Folders to scan")
    scan_parser.add_argument("--watch", action="store_true", help="Keep watching after scan")

    # search command
    search_parser = subparsers.add_parser("search", help="Search indexed files")

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show index statistics")

    args = parser.parse_args()

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "stats":
        cmd_stats(args)
    else:
        # Default — show menu
        print("\n  HUMPHI AI — File Search")
        print("  Usage:")
        print("    python main.py scan          — index your files")
        print("    python main.py scan --watch  — index + watch for changes")
        print("    python main.py search        — search your files")
        print("    python main.py stats         — show index info\n")


if __name__ == "__main__":
    main()
