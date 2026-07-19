"""Google Drive slideshow schemas (was the /CS feature)."""

from pydantic import BaseModel


class DriveImage(BaseModel):
    id: str
    name: str
