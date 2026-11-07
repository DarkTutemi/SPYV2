"""Data Sources API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import DataSource
from app.schemas.schemas import DataSourceCreate, DataSourceRead

router = APIRouter()


@router.get("/", response_model=list[DataSourceRead])
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DataSource).order_by(DataSource.created_at.desc()))
    return [DataSourceRead.model_validate(s) for s in result.scalars().all()]


@router.post("/", response_model=DataSourceRead, status_code=201)
async def create_source(payload: DataSourceCreate, db: AsyncSession = Depends(get_db)):
    source = DataSource(**payload.model_dump())
    db.add(source)
    await db.flush()
    await db.refresh(source)
    return DataSourceRead.model_validate(source)


@router.get("/{source_id}", response_model=DataSourceRead)
async def get_source(source_id: str, db: AsyncSession = Depends(get_db)):
    source = await db.get(DataSource, source_id)
    if not source:
        raise HTTPException(404, "Data source not found")
    return DataSourceRead.model_validate(source)

