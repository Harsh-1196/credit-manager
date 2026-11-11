from fastapi import APIRouter

from app.api.v1.endpoints import auth, groups, health, ledger, loans, meetings, members, savings, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(groups.router, prefix="/groups", tags=["groups"])
api_router.include_router(members.router, tags=["members"])
api_router.include_router(ledger.router, tags=["ledger"])
api_router.include_router(savings.router, tags=["savings"])
api_router.include_router(meetings.router, tags=["meetings"])
api_router.include_router(loans.router, tags=["loans"])
