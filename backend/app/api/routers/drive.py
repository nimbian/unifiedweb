"""Drive slideshow router (ports /CS, /api/cs/images, /image/<file_id>).

  GET /api/drive/images          -> list of image {id, name}
  GET /api/drive/image/{file_id} -> streamed image bytes (proxied from Drive)
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.dependencies.services import DriveServiceDep
from app.core.logging import get_logger
from app.schemas.drive import DriveImage

logger = get_logger(__name__)
router = APIRouter(prefix="/drive", tags=["drive"])


@router.get("/images", response_model=list[DriveImage], summary="List slideshow images")
def list_images(service: DriveServiceDep) -> list[DriveImage]:
    try:
        return service.list_images()
    except Exception as exc:  # noqa: BLE001 — mirror legacy broad handling, but logged
        logger.exception("Failed to list Drive images")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/image/{file_id}", summary="Proxy a single Drive image")
def get_image(file_id: str, service: DriveServiceDep) -> StreamingResponse:
    try:
        stream, mime = service.stream_image(file_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to serve Drive image %s: %s", file_id, exc)
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Image not found") from exc
    return StreamingResponse(stream, media_type=mime)
