from fastapi import APIRouter, Depends, HTTPException
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.services.reservations import calculate_monthly_revenue
from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant could not be resolved")
    
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    total_revenue = Decimal(str(revenue_data['total'])).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": float(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }


@router.get("/dashboard/monthly-summary")
async def get_monthly_dashboard_summary(
    property_id: str,
    month: int,
    year: int,
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant could not be resolved")

    try:
        from sqlalchemy import text
        from app.core.database_pool import db_pool

        if db_pool.session_factory is None:
            await db_pool.initialize()
        if db_pool.session_factory is None:
            raise RuntimeError("Database pool not available")

        session = await db_pool.get_session()
        async with session:
            result = await session.execute(text("""
                SELECT timezone
                FROM properties
                WHERE id = :property_id AND tenant_id = :tenant_id
            """), {"property_id": property_id, "tenant_id": tenant_id})
            property_row = result.fetchone()

        if not property_row:
            raise HTTPException(status_code=404, detail="Property not found")

        total = await calculate_monthly_revenue(
            property_id,
            month,
            year,
            tenant_id,
            property_row.timezone,
        )
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "property_id": property_id,
            "month": month,
            "year": year,
            "total_revenue": float(total),
            "currency": "USD",
        }
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=503, detail="Monthly revenue is unavailable") from error


@router.get("/properties")
async def get_properties(
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant could not be resolved")

    try:
        from sqlalchemy import text
        from app.core.database_pool import db_pool

        if db_pool.session_factory is None:
            await db_pool.initialize()
        if db_pool.session_factory is None:
            raise RuntimeError("Database pool not available")

        session = await db_pool.get_session()
        async with session:
            result = await session.execute(text("""
                SELECT id, name, timezone
                FROM properties
                WHERE tenant_id = :tenant_id
                ORDER BY name
            """), {"tenant_id": tenant_id})
            items = [dict(row._mapping) for row in result]

        return {"items": items, "total": len(items)}
    except Exception as error:
        raise HTTPException(status_code=503, detail="Properties are unavailable") from error
