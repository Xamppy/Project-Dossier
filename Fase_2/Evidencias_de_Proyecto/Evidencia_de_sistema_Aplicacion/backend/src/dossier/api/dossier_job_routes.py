"""API de jobs de generación asíncrona de dossiers."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dossier.api.auth_routes import (
    OrgAuthContext,
    get_current_user_and_org,
    get_db_if_configured,
    require_mutator,
)
from dossier.db.models import DossierGenerationJob, Organization, User
from dossier.services.dossier_generation_job_service import (
    cancel_dossier_generation_job,
    list_jobs_for_user,
    serialize_job,
)

router = APIRouter(tags=["Dossier jobs"])


@router.get("/dossier-generation-jobs")
def api_list_dossier_generation_jobs(
    user_org: Annotated[tuple[User, Organization], Depends(get_current_user_and_org)],
    db: Session = Depends(get_db_if_configured),
    active_only: bool = Query(True, description="Solo jobs en cola o en ejecución"),
    limit: int = Query(30, ge=1, le=100),
):
    user, org = user_org
    jobs = list_jobs_for_user(
        db,
        user_id=user.id,
        org_id=org.id,
        active_only=active_only,
        limit=limit,
    )
    return {"jobs": [serialize_job(j) for j in jobs]}


@router.get("/dossier-generation-jobs/{job_id}")
def api_get_dossier_generation_job(
    job_id: UUID,
    user_org: Annotated[tuple[User, Organization], Depends(get_current_user_and_org)],
    db: Session = Depends(get_db_if_configured),
):
    user, org = user_org
    job = db.get(DossierGenerationJob, job_id)
    if job is None or job.organization_id != org.id or job.requested_by_user_id != user.id:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    return serialize_job(job)


@router.post("/dossier-generation-jobs/{job_id}/cancel")
def api_cancel_dossier_generation_job(
    job_id: UUID,
    ctx: Annotated[OrgAuthContext, Depends(require_mutator)],
    db: Session = Depends(get_db_if_configured),
):
    user, org = ctx.user, ctx.org
    job = db.get(DossierGenerationJob, job_id)
    if job is None or job.organization_id != org.id or job.requested_by_user_id != user.id:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    job = cancel_dossier_generation_job(db, job=job)
    return serialize_job(job)
