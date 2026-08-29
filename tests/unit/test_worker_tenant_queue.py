"""Worker routing tests for the tenant-scoped durable job store."""

from __future__ import annotations

from zcoder.domain.models.tenant import EnterpriseRole, RequestContext
from zcoder.services.agent_runtime import Job, JobStatus
from zcoder.worker.process import Worker


class FakeTenantStore:
    def __init__(self) -> None:
        self.claims: list[tuple[RequestContext, str, float]] = []
        self.mutations: list[tuple[RequestContext, str, str, int, JobStatus, float]] = []
        self.renewals: list[tuple[RequestContext, str, str, int, float]] = []

    def claim_job_scoped(self, ctx: RequestContext, worker_id: str, lease_duration: float):
        self.claims.append((ctx, worker_id, lease_duration))
        return Job(id="job-1", task="run", status=JobStatus.RUNNING), 3

    def mutate_job_scoped(
        self,
        ctx: RequestContext,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        status: JobStatus,
        cost_usd: float,
    ) -> bool:
        self.mutations.append((ctx, job_id, worker_id, fencing_token, status, cost_usd))
        return True

    def renew_lease(
        self,
        ctx: RequestContext,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        lease_duration: float,
    ) -> bool:
        self.renewals.append((ctx, job_id, worker_id, fencing_token, lease_duration))
        return True


def configured_worker(store: FakeTenantStore) -> Worker:
    worker = Worker.__new__(Worker)
    worker._store = store
    worker._tenant_context = RequestContext(
        principal_id="worker-1",
        organization_id="org-1",
        role=EnterpriseRole.OPERATOR,
    )
    worker.worker_id = "worker-1"
    worker.lease_duration = 45.0
    return worker


def test_worker_routes_claim_mutation_and_lease_renewal_through_tenant_context() -> None:
    store = FakeTenantStore()
    worker = configured_worker(store)

    claimed = worker._claim_job()
    mutated = worker._mutate_job("job-1", 3, JobStatus.SUCCEEDED, 0.25)
    renewed = worker._renew_job_lease("job-1", 3)

    assert claimed is not None and claimed[0].id == "job-1"
    assert mutated is True
    assert renewed is True
    assert store.claims[0][0].organization_id == "org-1"
    assert store.mutations[0][4] == JobStatus.SUCCEEDED
    assert store.renewals[0][0].organization_id == "org-1"
