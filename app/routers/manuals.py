from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.services.azure_search_service import AzureSearchService

router = APIRouter()
search_service = AzureSearchService()

@router.get("/list_manuals")
async def list_manuals():
    """Lista todos los manuales disponibles"""
    manuals = await search_service.search_manuals()
    return {"manuals": manuals}

@router.get("/search_manuals/{query}")
async def search_manuals(query: str):
    """Busca manuales por texto"""
    manuals = await search_service.search_manuals(query)
    return {"manuals": manuals}

@router.get("/manual/{model}")
async def get_manual(model: str):
    """Obtiene un manual específico por modelo"""
    manual = await search_service.get_manual_by_model(model)
    if not manual:
        raise HTTPException(status_code=404, detail="Manual not found")
    return manual 