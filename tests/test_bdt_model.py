from datetime import datetime, timedelta
import numpy as np

# 假设 BDTModel 类已定义
valuation_date = datetime(2025, 1, 1)
time_points = [valuation_date + timedelta(days=365*i) for i in range(4)]
spot_rates = [0.0, 0.03, 0.035, 0.04]  # 简化示例
volatilities = [0.0, 0.01, 0.015, 0.02]

# 初始化模型
bdt = BDTModel(
    valuation_date=valuation_date,
    time_points=time_points,
    spot_rates=spot_rates,
    volatilities=volatilities,
    day_count_convention="ACT/365"
)

# 构建利率树
bdt.build_tree()

# 设置债券现金流 (3年，每年5元利息，第3年100元本金)
cashflows = [
    (1, 5.0),
    (2, 5.0),
    (3, 105.0)  # 第3年最后一笔利息和本金
]

# 可赎回价格从第2年开始为102
call_schedule = [
    (2, 102.0),
    (3, 102.0)
]

# 定价
price = bdt.price_callable_bond(
    cashflows=cashflows,
    call_schedule=call_schedule,
    put_schedule=None  # 无回售
)

print(f"可赎回债券的价格为: {price:.4f}")
