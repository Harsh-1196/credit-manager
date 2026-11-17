from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    audit,
    auth,
    dashboard,
    groups,
    health,
    ledger,
    loans,
    meetings,
    members,
    reconciliation,
    reports,
    savings,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(audit.router, tags=["audit"])
api_router.include_router(reconciliation.router, tags=["reconciliation"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(groups.router, prefix="/groups", tags=["groups"])
api_router.include_router(members.router, tags=["members"])
api_router.include_router(ledger.router, tags=["ledger"])
api_router.include_router(savings.router, tags=["savings"])
api_router.include_router(meetings.router, tags=["meetings"])
api_router.include_router(loans.router, tags=["loans"])
