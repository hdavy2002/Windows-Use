"""
humphi_search/cloud_backup.py

Optional cloud backup of the file index metadata to Supabase.
Stores file metadata only — never file contents or actual files.
Allows search to work across devices if user logs into Humphi on multiple machines.

Setup:
1. Create a free Supabase project at supabase.com
2. Create a table called 'file_index' with this SQL:

    create table file_index (
        id uuid default gen_random_uuid() primary key,
        user_id text not null,
        device_id text not null,
        path text not null,
        filename text not null,
        extension text,
        folder text,
        file_type text,
        modified text,
        size_bytes bigint,
        indexed_at timestamp default now(),
        unique(user_id, device_id, path)
    );

3. Set environment variables:
    HUMPHI_SUPABASE_URL=https://yourproject.supabase.co
    HUMPHI_SUPABASE_KEY=your_anon_key
    HUMPHI_USER_ID=user_unique_id
    HUMPHI_DEVICE_ID=this_machine_name
"""

import os
import socket
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("humphi.cloud")

SUPABASE_URL = os.environ.get("HUMPHI_SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("HUMPHI_SUPABASE_KEY", "")
USER_ID = os.environ.get("HUMPHI_USER_ID", "local_user")
DEVICE_ID = os.environ.get("HUMPHI_DEVICE_ID", socket.gethostname())


class HumphiCloudBackup:
    """
    Syncs file index metadata to Supabase.
    Non-blocking — runs as background batch uploads.
    Gracefully skips if Supabase is not configured.
    """

    def __init__(self):
        self.enabled = bool(SUPABASE_URL and SUPABASE_KEY)
        self.client = None

        if self.enabled:
            try:
                from supabase import create_client
                self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
                log.info(f"Cloud backup enabled. Device: {DEVICE_ID}")
            except ImportError:
                log.warning("supabase-py not installed. Run: pip install supabase")
                self.enabled = False
            except Exception as e:
                log.warning(f"Cloud backup init failed: {e}")
                self.enabled = False
        else:
            log.info("Cloud backup not configured. Running local only.")

    def backup_file(self, metadata: dict):
        """Upload a single file's metadata to Supabase."""
        if not self.enabled or not self.client:
            return

        try:
            self.client.table("file_index").upsert({
                "user_id": USER_ID,
                "device_id": DEVICE_ID,
                "path": metadata.get("path", ""),
                "filename": metadata.get("filename", ""),
                "extension": metadata.get("extension", ""),
                "folder": metadata.get("folder", ""),
                "file_type": metadata.get("type", ""),
                "modified": metadata.get("modified", ""),
                "size_bytes": metadata.get("size_bytes", 0),
            }, on_conflict="user_id,device_id,path").execute()
        except Exception as e:
            log.debug(f"Cloud backup error: {e}")

    def backup_batch(self, metadata_list: list):
        """Upload a batch of file metadata records."""
        if not self.enabled or not self.client or not metadata_list:
            return

        try:
            records = [{
                "user_id": USER_ID,
                "device_id": DEVICE_ID,
                "path": m.get("path", ""),
                "filename": m.get("filename", ""),
                "extension": m.get("extension", ""),
                "folder": m.get("folder", ""),
                "file_type": m.get("type", ""),
                "modified": m.get("modified", ""),
                "size_bytes": m.get("size_bytes", 0),
            } for m in metadata_list]

            self.client.table("file_index").upsert(
                records,
                on_conflict="user_id,device_id,path"
            ).execute()

            log.info(f"Cloud: backed up {len(records)} records")
        except Exception as e:
            log.debug(f"Cloud batch backup error: {e}")

    def remove_file(self, path: str):
        """Remove a file record from cloud when deleted locally."""
        if not self.enabled or not self.client:
            return
        try:
            self.client.table("file_index").delete().match({
                "user_id": USER_ID,
                "device_id": DEVICE_ID,
                "path": path,
            }).execute()
        except Exception as e:
            log.debug(f"Cloud remove error: {e}")

    def is_enabled(self) -> bool:
        return self.enabled
