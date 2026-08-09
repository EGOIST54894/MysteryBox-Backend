"""
模拟支付页面 API

GET /mock-pay?order_id=X&token=Y
返回一个美观的HTML模拟支付页面，用于开发调试。

页面功能：
- 显示订单金额
- 30秒支付倒计时
- "确认支付"按钮和"取消"按钮
- 点击确认后自动POST回调 /api/v1/payments/callback
- 品牌色 #FF6B35
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db

router = APIRouter()

MOCK_PAY_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>模拟支付 - 外卖盲盒</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                         "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue",
                         Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #fff5f0 0%, #ffe8dc 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .pay-card {
            background: #ffffff;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(255, 107, 53, 0.15),
                        0 8px 20px rgba(0, 0, 0, 0.06);
            width: 100%;
            max-width: 420px;
            overflow: hidden;
        }
        .pay-header {
            background: linear-gradient(135deg, #FF6B35 0%, #ff8c5a 100%);
            padding: 32px 28px 28px;
            text-align: center;
            color: #ffffff;
        }
        .pay-header .brand {
            font-size: 22px;
            font-weight: 700;
            letter-spacing: 2px;
            margin-bottom: 8px;
        }
        .pay-header .subtitle {
            font-size: 13px;
            opacity: 0.85;
        }
        .pay-body {
            padding: 32px 28px;
        }
        .amount-section {
            text-align: center;
            margin-bottom: 28px;
        }
        .amount-label {
            font-size: 14px;
            color: #999;
            margin-bottom: 8px;
        }
        .amount-value {
            font-size: 42px;
            font-weight: 700;
            color: #FF6B35;
            letter-spacing: 1px;
        }
        .amount-value .currency {
            font-size: 22px;
            font-weight: 500;
            vertical-align: top;
            margin-right: 4px;
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid #f5f5f5;
            font-size: 14px;
        }
        .info-row .label {
            color: #999;
        }
        .info-row .value {
            color: #333;
            font-weight: 500;
        }
        .countdown-section {
            text-align: center;
            margin: 24px 0;
        }
        .countdown-circle {
            display: inline-flex;
            justify-content: center;
            align-items: center;
            width: 72px;
            height: 72px;
            border-radius: 50%;
            border: 3px solid #FF6B35;
            color: #FF6B35;
            font-size: 24px;
            font-weight: 700;
            transition: all 0.3s ease;
        }
        .countdown-circle.warning {
            border-color: #e74c3c;
            color: #e74c3c;
            animation: pulse 1s infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.06); }
        }
        .countdown-label {
            font-size: 13px;
            color: #999;
            margin-top: 8px;
        }
        .btn-group {
            display: flex;
            gap: 14px;
            margin-top: 28px;
        }
        .btn {
            flex: 1;
            padding: 14px 0;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.25s ease;
            letter-spacing: 1px;
        }
        .btn:active {
            transform: scale(0.97);
        }
        .btn-primary {
            background: linear-gradient(135deg, #FF6B35 0%, #ff8c5a 100%);
            color: #ffffff;
            box-shadow: 0 6px 20px rgba(255, 107, 53, 0.35);
        }
        .btn-primary:hover {
            box-shadow: 0 8px 28px rgba(255, 107, 53, 0.45);
            transform: translateY(-1px);
        }
        .btn-primary:disabled {
            background: #ccc;
            box-shadow: none;
            cursor: not-allowed;
            transform: none;
        }
        .btn-secondary {
            background: #f5f5f5;
            color: #666;
        }
        .btn-secondary:hover {
            background: #e8e8e8;
        }
        .result-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .result-overlay.show {
            display: flex;
        }
        .result-card {
            background: #ffffff;
            border-radius: 20px;
            padding: 40px 30px;
            text-align: center;
            max-width: 340px;
            width: 90%;
        }
        .result-icon {
            font-size: 60px;
            margin-bottom: 16px;
        }
        .result-title {
            font-size: 20px;
            font-weight: 700;
            color: #333;
            margin-bottom: 8px;
        }
        .result-msg {
            font-size: 14px;
            color: #999;
            margin-bottom: 20px;
            line-height: 1.6;
        }
        .footer-note {
            text-align: center;
            padding: 0 28px 24px;
            font-size: 12px;
            color: #bbb;
        }
        .spinner {
            display: none;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: #fff;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
            margin-right: 8px;
            vertical-align: middle;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="pay-card">
        <!-- 头部 -->
        <div class="pay-header">
            <div class="brand">外卖盲盒</div>
            <div class="subtitle">模拟支付 - 仅用于开发调试</div>
        </div>

        <!-- 主体 -->
        <div class="pay-body">
            <!-- 支付金额 -->
            <div class="amount-section">
                <div class="amount-label">支付金额</div>
                <div class="amount-value">
                    <span class="currency">¥</span>{{amount}}
                </div>
            </div>

            <!-- 订单信息 -->
            <div class="info-row">
                <span class="label">订单编号</span>
                <span class="value">{{order_no}}</span>
            </div>
            <div class="info-row">
                <span class="label">支付方式</span>
                <span class="value">模拟支付</span>
            </div>
            <div class="info-row">
                <span class="label">交易流水号</span>
                <span class="value" style="font-size:12px;">{{token}}</span>
            </div>

            <!-- 倒计时 -->
            <div class="countdown-section">
                <div class="countdown-circle" id="countdown">{{countdown}}</div>
                <div class="countdown-label">秒后自动关闭</div>
            </div>

            <!-- 按钮 -->
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="handleCancel()">取消支付</button>
                <button class="btn btn-primary" id="payBtn" onclick="handlePay()">
                    <span class="spinner" id="spinner"></span>
                    确认支付
                </button>
            </div>
        </div>

        <!-- 底部提示 -->
        <div class="footer-note">
            此为模拟支付环境，不会产生真实交易
        </div>
    </div>

    <!-- 结果弹窗 -->
    <div class="result-overlay" id="resultOverlay">
        <div class="result-card">
            <div class="result-icon" id="resultIcon"></div>
            <div class="result-title" id="resultTitle"></div>
            <div class="result-msg" id="resultMsg"></div>
            <button class="btn btn-primary" onclick="closeResult()" style="width:100%;">确定</button>
        </div>
    </div>

    <script>
        // 从URL中解析参数及后台数据
        var orderId = "{{order_id}}";
        var token = "{{token}}";
        var countdown = {{countdown}};
        var countdownTimer = null;
        var isPaid = false;

        // 倒计时逻辑
        function startCountdown() {
            var el = document.getElementById('countdown');
            countdownTimer = setInterval(function() {
                countdown--;
                el.textContent = countdown;
                if (countdown <= 10) {
                    el.parentElement.querySelector('.countdown-circle').classList.add('warning');
                }
                if (countdown <= 0) {
                    clearInterval(countdownTimer);
                    if (!isPaid) {
                        showResult('timeout');
                    }
                }
            }, 1000);
        }

        // 确认支付
        function handlePay() {
            if (isPaid) return;
            var btn = document.getElementById('payBtn');
            var spinner = document.getElementById('spinner');
            btn.disabled = true;
            spinner.style.display = 'inline-block';

            // 模拟网络请求
            fetch('/api/v1/payments/callback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    order_id: parseInt(orderId),
                    token: token
                })
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                spinner.style.display = 'none';
                if (data.code === 0) {
                    isPaid = true;
                    clearInterval(countdownTimer);
                    showResult('success');
                } else {
                    btn.disabled = false;
                    showResult('fail', data.message || '支付失败，请重试');
                }
            })
            .catch(function(err) {
                spinner.style.display = 'none';
                btn.disabled = false;
                showResult('fail', '网络错误，请重试');
                console.error('支付请求失败:', err);
            });
        }

        // 取消支付
        function handleCancel() {
            if (isPaid) return;
            clearInterval(countdownTimer);
            showResult('cancel');
        }

        // 显示结果弹窗
        function showResult(type, msg) {
            var overlay = document.getElementById('resultOverlay');
            var icon = document.getElementById('resultIcon');
            var title = document.getElementById('resultTitle');
            var message = document.getElementById('resultMsg');

            overlay.classList.add('show');

            switch(type) {
                case 'success':
                    icon.textContent = '✅';
                    title.textContent = '支付成功';
                    message.textContent = '恭喜！支付已完成，您的订单已生效。\\n请等待商家确认订单。';
                    break;
                case 'timeout':
                    icon.textContent = '⏰';
                    title.textContent = '支付超时';
                    message.textContent = '支付超时，请重新发起支付。';
                    break;
                case 'cancel':
                    icon.textContent = '❌';
                    title.textContent = '支付已取消';
                    message.textContent = '您已取消本次支付。';
                    break;
                case 'fail':
                    icon.textContent = '⚠️';
                    title.textContent = '支付失败';
                    message.textContent = msg || '支付处理失败，请稍后重试。';
                    break;
            }
        }

        // 关闭结果弹窗
        function closeResult() {
            if (isPaid) {
                // 支付成功后，通知父窗口并关闭
                if (window.opener) {
                    window.opener.postMessage({ type: 'payment_success', order_id: orderId }, '*');
                }
                window.close();
            } else {
                // 未支付则返回上一页
                window.history.back();
            }
        }

        // 页面加载完成后启动倒计时
        window.addEventListener('DOMContentLoaded', function() {
            startCountdown();
        });
    </script>
</body>
</html>"""


@router.get("/mock-pay", summary="模拟支付页面", include_in_schema=True)
def mock_pay_page(
    order_id: int = Query(..., description="订单ID"),
    token: str = Query(..., description="支付令牌（交易流水号）"),
    db: Session = Depends(get_db),
):
    """
    模拟支付页面（GET 请求，返回 HTML）。

    显示订单金额、倒计时、确认支付和取消按钮。
    点击确认支付后，自动 POST 回调 /api/v1/payments/callback。

    Query 参数:
    - order_id: 订单ID
    - token: 支付令牌（即支付记录的 transaction_no）
    """
    from app.models.order import Order
    from app.models.payment import PaymentRecord

    # 校验支付令牌
    payment = (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.order_id == order_id,
            PaymentRecord.transaction_no == token,
            PaymentRecord.status == "pending",
        )
        .first()
    )
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="支付链接无效或已过期",
        )

    # 查询订单信息
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="订单不存在",
        )

    amount = f"{float(order.paid_amount):.2f}"
    order_no = order.order_no or f"#{order_id}"

    # 渲染HTML
    html = MOCK_PAY_HTML
    html = html.replace("{{amount}}", amount)
    html = html.replace("{{order_no}}", order_no)
    html = html.replace("{{order_id}}", str(order_id))
    html = html.replace("{{token}}", token)
    html = html.replace("{{countdown}}", "30")

    return HTMLResponse(content=html)
