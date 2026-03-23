"""
humphi_search/watcher.py

Real-time folder monitoring using Watchdog.
Automatically indexes new files and removes deleted ones.
Runs as a background thread.
"""

import time
import logging
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileDeletedEvent, FileModifiedEvent
from humphi_search.indexer import HumphiIndexer, SUPPORTED_EXTENSIONS, _should_skip

log = logging.getLogger("humphi.watcher")


class HumphiFileHandler(FileSystemEventHandler):

    def __init__(self, indexer: HumphiIndexer):
        self.indexer = indexer
        self._pending = {}  # path -> timestamp, for debouncing
        self._lock = threading.Lock()

    def on_created(self, event):
        if not event.is_directory:
            self._queue(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._queue(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            path = Path(event.src_path)
            self.indexer.remove_file(path)
            log.debug(f"Removed from index: {path.name}")

    def on_moved(self, event):
        if not event.is_directory:
            # Remove old path, index new path
            self.indexer.remove_file(Path(event.src_path))
            self._queue(event.dest_path)

    def _queue(self, path_str: str):
        """Debounce — wait 2 seconds before indexing to avoid partial writes."""
        with self._lock:
            self._pending[path_str] = time.time()

    def process_pending(self):
        """Call this in a loop to process debounced events."""
        now = time.time()
        with self._lock:
            ready = [p for p, t in self._pending.items() if now - t > 2.0]
            for p in ready:
                del self._pending[p]

        for path_str in ready:
            path = Path(path_str)
            if path.suffix.lower() in SUPPORTED_EXTENSIONS and not _should_skip(path):
                indexed = self.indexer.index_file(path)
                if indexed:
                    log.info(f"Auto-indexed: {path.name}")


class HumphiWatcher:
    """
    Watches folders for file changes and keeps the index up to date.
    Runs in a background thread — non-blocking.
    """

    def __init__(self, folders: list, indexer: HumphiIndexer):
        self.folders = [Path(f) for f in folders]
        self.indexer = indexer
        self.observer = Observer()
        self.handler = HumphiFileHandler(indexer)
        self._running = False
        self._thread = None

    def start(self):
        for folder in self.folders:
            if folder.exists():
                self.observer.schedule(self.handler, str(folder), recursive=True)
                log.info(f"Watching: {folder}")

        self.observer.start()
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        log.info("File watcher started")

    def _process_loop(self):
        while self._running:
            self.handler.process_pending()
            time.sleep(1)

    def stop(self):
        self._running = False
        self.observer.stop()
        self.observer.join()
        log.info("File watcher stopped")
