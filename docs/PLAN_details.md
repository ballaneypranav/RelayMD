# Implementation Plan for Job Lifecycle Status Reporting

This document outlines the detailed steps to implement the changes specified in `PLAN.md` for accurate job lifecycle status reporting in RelayMD.

---

## 1. **Fix Alembic Migration**

**Issue**: Broken migration due to invalid revision ID and SQLite incompatibility.

**Steps**:
1. Generate a properly chained migration:
   ```bash
   export DATABASE_URL='sqlite+aiosqlite:////depot/plow/data/pballane/relaymd-service/db/relaymd.db'
   alembic revision --message "Add job lifecycle fields" --depends f8da36c3c972
   ```
2. Manually correct the migration script (e.g., `alembic/versions/new_revision.py`):
   ```python
   def upgrade():
       op.add_column('job', sa.Column('assigned_at', sa.DateTime(), nullable=True))
       op.add_column('job', sa.Column('started_at', sa.DateTime(), nullable=True))
       op.add_column('job', sa.Column('status_changed_at', sa.DateTime(), nullable=False))
       # Backfill in a single pass
       op.execute(
         "UPDATE job SET \n"
         "status_changed_at = updated_at, \n"
         "assigned_at = CASE WHEN status IN ('assigned', 'running') THEN updated_at ELSE NULL END"
       )
   
   def downgrade():
       op.drop_column('job', 'assigned_at')
       op.drop_column('job', 'started_at')
       op.drop_column('job', 'status_changed_at')
   ```
3. Apply migrations explicitly during deployment (not at app startup).

---

## 2. **Update Shared Models**

**Issue**: `JobRead` lacks new fields, breaking API/frontend compatibility.

**Steps**:
1. Edit `packages/relaymd-core/src/relaymd/models/job.py` to add fields to `JobRead`:
   ```python
   class JobRead(SQLModel):
       # ... existing fields ...
       assigned_at: datetime | None = None
       started_at: datetime | None = None
       status_changed_at: datetime
   ```

---

## 3. **Implement Transition Logic**

**Issue**: Timestamps not set during job transitions.

**Steps**:
1. **Assignment Service**: Update `assigned_at` and `status_changed_at` during assignment:
   ```python
   # src/relaymd/orchestrator/services/assignment_service.py
   async def assign_job(job: Job, worker_id: uuid.UUID) -> Job:
       job.status = JobStatus.assigned
       job.assigned_worker_id = worker_id
       job.assigned_at = utcnow_naive()
       job.status_changed_at = utcnow_naive()
       await db.commit()
   ```
2. **Job Transitions**: Update `status_changed_at` for all status changes:
   ```python
   # src/relaymd/orchestrator/services/job_transitions.py
   async def update_job_status(job: Job, new_status: JobStatus) -> Job:
       job.status = new_status
       job.status_changed_at = utcnow_naive()
       await db.commit()
   ```

---

## 4. **Add Worker API Endpoint**

**Issue**: Missing `/jobs/{job_id}/start` endpoint.

**Steps**:
1. Add the endpoint in `src/relaymd/orchestrator/routers/jobs_worker.py`:
   ```python
   @router.post("/jobs/{job_id}/start", status_code=204)
   async def start_job(job_id: uuid.UUID, current_user: Worker = Depends(get_current_worker)):
       await JobTransitionService.mark_job_running(job_id, worker_id=current_user.id)
   ```
2. Regenerate the API client:
   ```bash
   ./scripts/generate_api_client.sh
   ```

---

## 5. **Update Worker Implementation**

**Issue**: Worker does not report job start.

**Steps**:
1. Call `start_job` after execution begins in `packages/relaymd-worker/src/relaymd/worker/main.py`:
   ```python
   async def _run_assigned_job(job: JobRead):
       execution.start()  # Begin workload
       await gateway.start_job(job.id)  # Report running status
   ```

---

## 6. **Fix Frontend Time Calculations**

**Issue**: `time_in_status` uses `updated_at` instead of `status_changed_at`.

**Steps**:
1. Update `frontend/src/format.ts`:
   ```typescript
   function buildJobRows(jobs: JobRead[]): JobRow[] {
       return jobs.map(job => ({
           // ... existing fields ...
           time_in_status: Math.floor((Date.now() - job.status_changed_at.getTime()) / 1000),
       }));
   }
   ```

---

## 7. **Cleanup**

- Delete `test_db.py` (scratch file).
- Commit changes and bump version:
  ```bash
  git add .
  git commit -m "Fix job lifecycle status reporting"
  make release-cli VERSION=0.1.46
  ```

---

## **Validation Commands**

Run the following to verify changes:
```bash
uv run pytest tests/orchestrator packages/relaymd-worker/tests
uv run pytest tests/cli
uv run ruff check .
uv run pyright
cd frontend && npm --cache ./.npm run build && npm --cache ./.npm test
```

This plan ensures all layers (DB, API, worker, frontend) are updated consistently, resolving the original issues in `PLAN.md`.