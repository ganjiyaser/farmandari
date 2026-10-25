import os
import shutil
import uuid
import mimetypes
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from core.config import settings
from core.database import get_current_files_dir
from models.models import ContactFile
from services.repositories import file_repo

# Characters Windows rejects in file names (also illegal on SMB shares).
_INVALID_NAME_CHARS = '<>:"/\\|?*'


def safe_filename(name: str, fallback: str = "file") -> str:
    """Strip path separators and reserved characters from a user-supplied name.

    Export/download paths were built straight from ``original_name`` / group
    names, so a value like ``..\\..\\x`` wrote outside the target directory and
    any of ``<>:"/\\|?*`` made the save fail with an opaque OSError.
    """
    cleaned = "".join(
        "_" if ch in _INVALID_NAME_CHARS or ord(ch) < 32 else ch
        for ch in str(name or "")
    ).strip().strip(".")
    if not cleaned:
        cleaned = fallback
    # Never allow a traversal component.
    if cleaned in (".", ".."):
        cleaned = fallback
    return cleaned[:180]


class FileService:
    def __init__(self):
        # Resolved per call: the app stores attachments in
        # FILES_DIR/<username> (or SHARED_FILES_DIR/<username>). Capturing
        # settings.FILES_DIR at import time wrote every user's files into the
        # shared root, which users_page cleanup/export never touched.
        pass

    @property
    def files_dir(self) -> Path:
        return get_current_files_dir()

    def upload_file(self, contact_id: int, file_path: str, category: str = "document",
                    description: str = None, letter_number: str = None,
                    letter_date: datetime = None, letter_subject: str = None,
                    letter_type: str = None, sender: str = None,
                    receiver: str = None, uploaded_by: str = None,
                    is_confidential: bool = False, tags: list = None) -> ContactFile:
        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = src.suffix.lower()
        if ext not in settings.ALLOWED_FILE_EXTENSIONS:
            raise ValueError(f"File extension not allowed: {ext}")

        file_size = src.stat().st_size
        if file_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"File too large: {file_size / 1024 / 1024:.1f}MB")

        file_uuid = str(uuid.uuid4())
        contact_dir = self.files_dir / str(contact_id)
        contact_dir.mkdir(parents=True, exist_ok=True)

        new_filename = f"{file_uuid}{ext}"
        dst = contact_dir / new_filename
        shutil.copy2(str(src), str(dst))

        mime_type, _ = mimetypes.guess_type(src.name)

        try:
            return file_repo.create(
                uuid=file_uuid,
                contact_id=contact_id,
                file_name=new_filename,
                original_name=safe_filename(src.name, fallback=new_filename),
                file_path=str(dst),
                file_size=file_size,
                mime_type=mime_type,
                file_extension=ext,
                file_category=category,
                description=description,
                letter_number=letter_number,
                letter_date=letter_date,
                letter_subject=letter_subject,
                letter_type=letter_type,
                sender=sender,
                receiver=receiver,
                uploaded_by=uploaded_by,
                is_confidential=is_confidential,
                tags=tags or [],
            )
        except Exception:
            # Roll back the copy so a failed insert (e.g. bad contact_id FK)
            # doesn't leave an orphan file behind forever.
            try:
                dst.unlink()
            except OSError:
                pass
            raise
    
    def download_file(self, file_id: int, dest_path: str = None) -> str:
        contact_file = file_repo.get_by_id(file_id)
        if not contact_file:
            raise FileNotFoundError(f"File not found with id: {file_id}")
        
        src = Path(contact_file.file_path)
        if not src.exists():
            raise FileNotFoundError(f"File not found on disk: {src}")
        
        if dest_path:
            dest = Path(dest_path)
        else:
            dest = Path(settings.EXPORT_DIR) / safe_filename(
                contact_file.original_name, fallback=contact_file.file_name
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        return str(dest)

    def delete_file(self, file_id: int) -> bool:
        contact_file = file_repo.get_by_id(file_id)
        if not contact_file:
            return False

        file_path = Path(contact_file.file_path)
        # Remove the record first: a failed unlink must not leave a dangling
        # row that points at a file which then can never be downloaded.
        removed = file_repo.delete(file_id)
        if not removed:
            return False
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError:
            # Best effort -- the orphan file is harmless and can be cleaned up
            # manually, unlike a broken DB record.
            import logging
            logging.getLogger(__name__).warning(
                "File record %s deleted but the file on disk could not be "
                "removed: %s", file_id, file_path
            )
        return True
    
    def get_file_info(self, file_id: int) -> Optional[ContactFile]:
        return file_repo.get_by_id(file_id)
    
    def get_contact_files(self, contact_id: int, category: str = None) -> List[ContactFile]:
        return file_repo.get_by_contact(contact_id, category)
    
    def search_files(self, query: str, contact_id: int = None) -> List[ContactFile]:
        return file_repo.search_files(query, contact_id)
    
    def get_letters(self, contact_id: int = None, letter_type: str = None) -> List[ContactFile]:
        return file_repo.get_letters(contact_id, letter_type)
    
    def copy_file_to_clipboard(self, file_id: int) -> str:
        contact_file = file_repo.get_by_id(file_id)
        if not contact_file:
            raise FileNotFoundError(f"File not found")
        
        temp_path = Path(settings.EXPORT_DIR) / "temp" / safe_filename(
            contact_file.original_name, fallback=contact_file.file_name
        )
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(contact_file.file_path, str(temp_path))
        return str(temp_path)


file_service = FileService()