from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from zoneinfo import ZoneInfo

async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str,
    property_timezone: str = "UTC",
    db_session=None,
) -> Decimal:
    """
    Calculates revenue for a specific month.
    """
    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")

    local_timezone = ZoneInfo(property_timezone)
    start_date = datetime(year, month, 1, tzinfo=local_timezone)
    if month < 12:
        end_date = datetime(year, month + 1, 1, tzinfo=local_timezone)
    else:
        end_date = datetime(year + 1, 1, 1, tzinfo=local_timezone)

    if db_session is None:
        from app.core.database_pool import db_pool

        if db_pool.session_factory is None:
            await db_pool.initialize()
        if db_pool.session_factory is None:
            raise RuntimeError("Revenue database is unavailable")

        session = await db_pool.get_session()
        async with session:
            return await calculate_monthly_revenue(
                property_id,
                month,
                year,
                tenant_id,
                property_timezone,
                session,
            )
        
    from sqlalchemy import text

    result = await db_session.execute(text("""
        SELECT COALESCE(SUM(total_amount), 0) AS total
        FROM reservations
        WHERE property_id = :property_id
          AND tenant_id = :tenant_id
          AND check_in_date >= :start_date
          AND check_in_date < :end_date
    """), {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "start_date": start_date,
        "end_date": end_date,
    })
    return Decimal(str(result.scalar_one()))

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Import database pool
        from app.core.database_pool import db_pool
        
        # Initialize pool if needed
        if db_pool.session_factory is None:
            await db_pool.initialize()
        
        if db_pool.session_factory:
            session = await db_pool.get_session()
            async with session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                query = text("""
                    SELECT 
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations 
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY property_id
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id
                })
                row = result.fetchone()
                
                if row:
                    total_revenue = Decimal(str(row.total_revenue))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": "USD", 
                        "count": row.reservation_count
                    }
                else:
                    # No reservations found for this property
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        raise RuntimeError("Revenue database is unavailable") from e
