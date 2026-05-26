"""微信支付回调 Webhook。（Task 6 实现）"""
from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
