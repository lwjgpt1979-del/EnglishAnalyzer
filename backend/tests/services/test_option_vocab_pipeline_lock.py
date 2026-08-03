"""选项词跑批:同范围防重复开任务。"""
import uuid

from app.services import option_vocab_pipeline_service as pipe


def _job(**kw):
    base = {
        "status": "running",
        "region_code": "320200",
        "region_name": "无锡市",
        "year": 2024,
        "paper_ids": ["p1", "p2"],
    }
    base.update(kw)
    return base


def test_scope_conflicts_same_region_year():
    job = _job()
    assert pipe._scope_conflicts(
        job, region_code="320200", year=2024, paper_ids=[],
    )
    assert not pipe._scope_conflicts(
        job, region_code="320200", year=2023, paper_ids=[],
    )
    assert not pipe._scope_conflicts(
        job, region_code="320100", year=2024, paper_ids=[],
    )


def test_scope_conflicts_paper_overlap():
    pid = uuid.UUID("00000000-0000-0000-0000-00000000000a")
    job = _job(region_code=None, year=None, paper_ids=[str(pid), "b"])
    assert pipe._scope_conflicts(job, region_code=None, year=None, paper_ids=[pid])
    assert not pipe._scope_conflicts(
        job,
        region_code=None,
        year=None,
        paper_ids=[uuid.UUID("00000000-0000-0000-0000-000000000099")],
    )


def test_find_active_scope_job_skips_done():
    pipe._jobs.clear()
    pipe._jobs["done1"] = _job(status="done")
    pipe._jobs["run1"] = _job(status="running")
    found = pipe._find_active_scope_job(
        region_code="320200", year=2024, paper_ids=[],
    )
    assert found == "run1"
    pipe._jobs.clear()
