from fastapi import APIRouter, Depends, Query
from typing import List, Dict, Any
from datetime import datetime, timedelta
import random

from app.services.auth_service import get_current_active_user
from app.models.database import User

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/summary")
async def get_analytics_summary(current_user: User = Depends(get_current_active_user)):
    """Get high-level portfolio analytics summary."""
    # In a real app, this would aggregate data from the Transaction table
    return {
        "total_value_usd": 12847.32,
        "performance_24h": {
            "usd": 1247.50,
            "percentage": 10.7
        },
        "category_breakdown": [
            {"label": "DeFi", "value": 45, "color": "#7c3aed"},
            {"label": "Stablecoins", "value": 30, "color": "#10b981"},
            {"label": "NFTs", "value": 15, "color": "#f59e0b"},
            {"label": "Others", "value": 10, "color": "#6366f1"}
        ],
        "network_breakdown": [
            {"network": "Ethereum", "value": 6183.40},
            {"network": "Polygon", "value": 2987.50},
            {"network": "Solana", "value": 1909.92},
            {"network": "Stablecoins", "value": 1766.50}
        ]
    }

@router.get("/portfolio")
async def get_portfolio_history(
    period: str = Query("7d", regex="^(24h|7d|30d|90d|1y|all)$"),
    current_user: User = Depends(get_current_active_user)
):
    """Get portfolio value history points for charting."""
    # Simulate historical data
    points = 24 if period == "24h" else 30 if period == "30d" else 7
    base_val = 11000.0
    history = []
    
    current_time = datetime.now()
    for i in range(points):
        delta = timedelta(hours=i) if period == "24h" else timedelta(days=points-i)
        ts = (current_time - delta).isoformat()
        val = base_val + (random.random() * 2000) - 500
        history.append({"timestamp": ts, "value": round(val, 2)})
        base_val = val
        
    return {"history": history, "period": period}
