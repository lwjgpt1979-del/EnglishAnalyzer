"""分公司管理 + 城市归属 tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.exceptions import AppError

_TAG = "brtest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


async def _cleanup(db):
    await db.execute(text(
        "DELETE FROM branch_company_cities WHERE branch_company_id IN "
        "(SELECT id FROM branch_companies WHERE name LIKE :p)"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM branch_companies WHERE name LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_branch_crud_city_and_bank_encrypt():
    from app.services import branch_service as bs
    from app.models.d10_branch import BranchCompany

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            # 建分公司 + 银行账户加密
            b = await bs.create_branch(db, name=f"{_TAG}_sh", commission_rate=0.3,
                                       bank_name="ICBC", bank_account="6222000011112222")
            await db.flush()
            row = await db.get(BranchCompany, b.id)
            assert row.bank_account.startswith("v1:")          # 密文
            assert row.bank_account != "6222000011112222"

            # 列表不回明文，只给布尔
            items = await bs.list_branches(db)
            mine = [x for x in items if x["id"] == b.id][0]
            assert mine["bank_account_set"] is True
            assert "6222000011112222" not in str(mine)
            assert float(mine["commission_rate"]) == 0.3

            # 加城市归属
            c = await bs.add_city(db, b.id, city_code="BR_SH")
            await db.flush()
            # 同城市再归属另一家 → 拒
            b2 = await bs.create_branch(db, name=f"{_TAG}_sh2")
            await db.flush()
            with pytest.raises(AppError):
                await bs.add_city(db, b2.id, city_code="BR_SH")

            # 解除城市归属（置 effective_to，不物理删）
            await bs.remove_city(db, c.id)
            await db.flush()
            from app.models.d10_branch import BranchCompanyCity
            cc = await db.get(BranchCompanyCity, c.id)
            assert cc.effective_to is not None
            # 解除后可重新归属其他分公司
            c2 = await bs.add_city(db, b2.id, city_code="BR_SH")
            assert c2 is not None
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()
