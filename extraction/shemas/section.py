from pydantic import BaseModel
from typing import List, Optional


class Section(BaseModel):
    """
    Represents a structured section extracted from a document.
    This is the CONTRACT between extraction and ingestion.
    """

    id: str                      # unique identifier (uuid or hash)
    app: str                     # application name (e.g., "PARC-AUTO")

    title: str                   # section title
    content: str                 # full text content

    breadcrumb: List[str]        # hierarchy (e.g., ["Getting Started", "Login"])
    page: Optional[int] = None   # page number if available

    checksum: str                # used to detect updates / duplicates

    source_file: Optional[str] = None  # original file name (PDF)