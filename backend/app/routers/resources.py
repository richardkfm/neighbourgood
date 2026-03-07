"""Resource CRUD endpoints with search, image upload, and category metadata."""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models.community import CommunityMember
from app.models.resource import Resource
from app.models.user import User
from app.services.activity import record_activity
from app.services.file_upload import ALLOWED_EXTENSIONS, ALLOWED_IMAGE_TYPES, validate_image_magic
from app.services.webhooks import dispatch_event
from app.schemas.resource import (
    CATEGORY_META,
    VALID_CATEGORIES,
    VALID_CONDITIONS,
    CategoryInfo,
    InventoryUpdate,
    ResourceCreate,
    ResourceList,
    ResourceOut,
    ResourceUpdate,
)

router = APIRouter(prefix="/resources", tags=["resources"])


def _resource_to_out(resource: Resource) -> dict:
    """Convert a Resource ORM object to a dict with image_url and inventory fields computed."""
    threshold = resource.reorder_threshold
    low_stock = (
        threshold is not None and resource.quantity_available <= threshold
    )
    return {
        "id": resource.id,
        "title": resource.title,
        "description": resource.description,
        "category": resource.category,
        "condition": resource.condition,
        "image_url": f"/resources/{resource.id}/image" if resource.image_path else None,
        "is_available": resource.is_available,
        "owner_id": resource.owner_id,
        "community_id": resource.community_id,
        "owner": resource.owner,
        "quantity_total": resource.quantity_total,
        "quantity_available": resource.quantity_available,
        "reorder_threshold": resource.reorder_threshold,
        "low_stock": low_stock,
        "created_at": resource.created_at,
        "updated_at": resource.updated_at,
    }


@router.get("/categories", response_model=list[CategoryInfo])
def list_categories():
    """Return all resource categories with labels and icon names."""
    return [
        CategoryInfo(value=k, label=v["label"], icon=v["icon"])
        for k, v in CATEGORY_META.items()
    ]


@router.get("", response_model=ResourceList)
def list_resources(
    category: str | None = Query(None),
    available: bool | None = Query(None),
    community_id: int | None = Query(None, description="Filter by community"),
    q: str | None = Query(None, min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """List resources with optional filters and text search.

    If authenticated and no community_id provided, shows resources from user's joined communities.
    If not authenticated or community_id provided, shows public community resources.
    """
    query = db.query(Resource).options(joinedload(Resource.owner))

    # Only show community-scoped resources
    query = query.filter(Resource.community_id.isnot(None))

    # Auto-filter by user's communities if logged in and no specific community requested
    if current_user is not None and community_id is None:
        user_community_ids = db.query(CommunityMember.community_id).filter(
            CommunityMember.user_id == current_user.id
        ).all()
        user_community_ids = [cid[0] for cid in user_community_ids]

        if user_community_ids:
            query = query.filter(Resource.community_id.in_(user_community_ids))
        else:
            # User not in any communities, return empty results
            query = query.filter(False)
    elif community_id is not None:
        query = query.filter(Resource.community_id == community_id)

    if category:
        query = query.filter(Resource.category == category)
    if available is not None:
        query = query.filter(Resource.is_available == available)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                Resource.title.ilike(pattern),
                Resource.description.ilike(pattern),
            )
        )

    total = query.count()
    items = query.order_by(Resource.created_at.desc()).offset(skip).limit(limit).all()
    return ResourceList(
        items=[ResourceOut(**_resource_to_out(r)) for r in items],
        total=total,
    )


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(
    body: ResourceCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new resource listing."""
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category. Must be one of: {VALID_CATEGORIES}",
        )
    if body.condition and body.condition not in VALID_CONDITIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid condition. Must be one of: {VALID_CONDITIONS}",
        )

    resource = Resource(
        title=body.title,
        description=body.description,
        category=body.category,
        condition=body.condition,
        owner_id=current_user.id,
        community_id=body.community_id,
        quantity_total=body.quantity_total,
        quantity_available=body.quantity_total,  # start fully stocked
        reorder_threshold=body.reorder_threshold,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    _ = resource.owner
    record_activity(
        db,
        event_type="resource_shared",
        summary=f"shared \"{resource.title}\"",
        actor_id=current_user.id,
        community_id=resource.community_id,
    )

    if resource.community_id:
        background_tasks.add_task(
            dispatch_event,
            db,
            "resource.shared",
            {"actor_name": current_user.display_name, "title": resource.title},
            [],
            resource.community_id,
        )

    return ResourceOut(**_resource_to_out(resource))


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(resource_id: int, db: Session = Depends(get_db)):
    """Get a single resource by ID."""
    resource = (
        db.query(Resource)
        .options(joinedload(Resource.owner))
        .filter(Resource.id == resource_id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return ResourceOut(**_resource_to_out(resource))


@router.patch("/{resource_id}", response_model=ResourceOut)
def update_resource(
    resource_id: int,
    body: ResourceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a resource (owner only)."""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if resource.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your resource")

    if body.title is not None:
        resource.title = body.title
    if body.description is not None:
        resource.description = body.description
    if body.category is not None:
        if body.category not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid category. Must be one of: {VALID_CATEGORIES}",
            )
        resource.category = body.category
    if body.condition is not None:
        if body.condition not in VALID_CONDITIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid condition. Must be one of: {VALID_CONDITIONS}",
            )
        resource.condition = body.condition
    if body.is_available is not None:
        resource.is_available = body.is_available
    if "reorder_threshold" in body.model_fields_set:
        resource.reorder_threshold = body.reorder_threshold

    db.commit()
    db.refresh(resource)
    _ = resource.owner
    return ResourceOut(**_resource_to_out(resource))


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a resource (owner only)."""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if resource.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your resource")
    if resource.image_path:
        try:
            os.remove(resource.image_path)
        except OSError:
            pass
    db.delete(resource)
    db.commit()


# ── Inventory management ───────────────────────────────────────────


@router.patch("/{resource_id}/inventory", response_model=ResourceOut)
def update_inventory(
    resource_id: int,
    body: InventoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually adjust the available stock count (owner only).

    Use this to correct inventory after physical stock-takes or when
    units are damaged / returned outside of the normal booking flow.
    quantity_available cannot exceed quantity_total.
    """
    resource = (
        db.query(Resource)
        .options(joinedload(Resource.owner))
        .filter(Resource.id == resource_id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if resource.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your resource")
    if body.quantity_available > resource.quantity_total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"quantity_available ({body.quantity_available}) cannot exceed quantity_total ({resource.quantity_total})",
        )

    resource.quantity_available = body.quantity_available
    # Auto-mark unavailable when stock is fully depleted
    if resource.quantity_available == 0:
        resource.is_available = False
    elif not resource.is_available:
        resource.is_available = True

    db.commit()
    db.refresh(resource)
    return ResourceOut(**_resource_to_out(resource))


# ── Image upload / download ────────────────────────────────────────


@router.post("/{resource_id}/image", response_model=ResourceOut)
async def upload_image(
    resource_id: int,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload an image for a resource (owner only). Replaces any existing image."""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if resource.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your resource")

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid image type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    contents = await file.read()
    if len(contents) > settings.max_image_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image too large. Max {settings.max_image_size // (1024*1024)} MB.",
        )

    # Validate magic bytes to prevent disguised file uploads
    if not validate_image_magic(contents):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File content does not match a valid image format",
        )

    # Remove old image
    if resource.image_path:
        try:
            os.remove(resource.image_path)
        except OSError:
            pass

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Sanitise extension – only allow known safe extensions
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    if ext not in ALLOWED_EXTENSIONS:
        ext = "jpg"
    filename = f"{resource_id}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = upload_dir / filename

    with open(filepath, "wb") as f:
        f.write(contents)

    resource.image_path = str(filepath)
    db.commit()
    db.refresh(resource)
    _ = resource.owner
    return ResourceOut(**_resource_to_out(resource))


@router.get("/{resource_id}/image")
def get_image(resource_id: int, db: Session = Depends(get_db)):
    """Serve the image file for a resource."""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource or not resource.image_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No image found")
    if not os.path.exists(resource.image_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file missing")
    return FileResponse(resource.image_path)
