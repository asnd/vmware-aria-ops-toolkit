"""V1 API router aggregator."""

from fastapi import APIRouter

from app.api.v1 import auth, jobs, nsxt, sites

# Create V1 API router
v1_router = APIRouter(prefix="/v1")

# Include all endpoint routers
v1_router.include_router(auth.router)
v1_router.include_router(jobs.router)
v1_router.include_router(sites.router)
v1_router.include_router(nsxt.router)

# TODO: Add AVI router when implemented
# from app.api.v1 import avi
# v1_router.include_router(avi.router)
