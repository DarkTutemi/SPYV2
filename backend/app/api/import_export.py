"""Import/Export API endpoints."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import DataSourceType
from app.schemas.schemas import ImportRequest, ImportResult
from app.services.import_service import ImportService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/json", response_model=ImportResult)
async def import_json(
    payload: ImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Import data from a JSON payload or file path."""
    service = ImportService(db)
    return await service.import_data(
        source_type=payload.source_type,
        data=payload.data,
        file_path=payload.file_path,
        options=payload.options,
    )


@router.post("/file", response_model=ImportResult)
async def import_file(
    file: UploadFile = File(...),
    source_type: str = Form("meta_ad_library"),
    db: AsyncSession = Depends(get_db),
):
    """Import data from an uploaded file (JSON, CSV, JSONL)."""
    # Save uploaded file temporarily
    import tempfile
    suffix = Path(file.filename).suffix if file.filename else ".json"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        stype = DataSourceType(source_type)
    except ValueError:
        stype = DataSourceType.MANUAL_IMPORT

    service = ImportService(db)
    result = await service.import_data(
        source_type=stype,
        file_path=tmp_path,
    )

    # Clean up temp file
    try:
        Path(tmp_path).unlink()
    except Exception:
        pass

    return result


@router.post("/meta-ads", response_model=ImportResult)
async def import_meta_ads(
    payload: ImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Import Meta Ad Library data specifically."""
    service = ImportService(db)
    return await service.import_data(
        source_type=DataSourceType.META_AD_LIBRARY,
        data=payload.data,
        file_path=payload.file_path,
        options=payload.options,
    )

