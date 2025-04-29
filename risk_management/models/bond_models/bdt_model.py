import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Union

logger = logging.getLogger(__name__)


class BDTModel:
    """黑-德曼-托伊(Black-Derman-Toy)模型实现

    用于可赎回/可回售债券的定价，基于利率的二叉树模型

    参考文献：
    [1] Black, F., Derman, E., and Toy, W. (1990). "A One-Factor Model of Interest
        Rates and Its Application to Treasury Bond Options." Financial Analysts Journal.
    [2] Hull, J. "Options, Futures, and Other Derivatives."
    """

    def __init__(self,
                 valuation_date: datetime,
                 time_points: List[datetime],
                 spot_rates: List[float],
                 volatilities: List[float],
                 day_count_convention: str = 'ACT/365',
                 calibration_tolerance: float = 1e-8,
                 max_calibration_iteration: int = 100,
                 u_bounds: Tuple[float, float] = (1e-4, 0.5)):
        """初始化BDT模型
        :param valuation_date: 估值日期
        :param time_points: 二叉树节点对应的日期
        :param spot_rates: 即期利率列表
        :param volatilities: 波动率列表
        :param day_count_convention: 天数计算方式，计日惯例为 'ACT/365'
        :param calibration_tolerance: 校准容差
        :param max_calibration_iteration: 最大校准迭代次数
        :param u_bounds: 中间利率u(i)的上下界
        """
        assert len(time_points) == len(spot_rates) == len(volatilities), \
            "时间点、即期利率和波动率列表长度不一致"
        assert len(time_points) >= 2, "时间点列表至少需要包含两个时间点"
        self.valuation_date = valuation_date
        self.time_points = time_points
        self.spot_rates = np.array(spot_rates)
        self.volatilities = np.array(volatilities)
        self.day_count_convention = day_count_convention
        self.calibration_tolerance = calibration_tolerance
        self.max_calibration_iteration = max_calibration_iteration
        self.u_bounds = u_bounds

        # 计算时间步长 (年化)
        self.time_steps = self._calculate_time_steps()

        # 树上的节点 (将在 build_tree 中填充)
        self.middle_rates = None  # 中间利率 u(i)
        self.short_rates = None  # 短期利率 r(i,j)
        self.discount_factors = None  # 折现因子 d(i,j)
        self.state_prices = None  # 状态价格 Q(i,j)
        self._n_steps = len(time_points)  # 二叉树的步数

    def _calculate_time_steps(self) -> List[float]:
        """计算每个时间点到上一个时间点的年化时间
        :return: 时间步长列表
        """
        time_steps = [0.0]
        for i in range(1, len(self.time_points)):
            delta = (self.time_points[i] - self.time_points[i - 1]).days
            if self.day_count_convention == 'ACT/365':
                time_steps.append(delta / 365.0)
            elif self.day_count_convention == 'ACT/360':
                time_steps.append(delta / 360.0)
            else:
                print("Unsupported day count convention, default using ACT/365")
                time_steps.append(delta / 365.0)
        return time_steps

    def build_tree(self) -> None:
        """构建BDT模型的二叉树
        1. 计算中间利率 u(i)
        2. 计算短期利率 r(i,j)
        3. 计算折现因子 d(i,j)
        4. 计算状态价格 Q(i,j)
        """
        n_steps = len(self.time_points)
        self.middle_rates = np.zeros(n_steps)
        self.short_rates = [np.zeros(2 * i + 1) for i in range(n_steps)]
        self.discount_factors = [np.zeros(2 * i + 1) for i in range(n_steps)]
        self.state_prices = [np.zeros(2 * i + 1) for i in range(n_steps)]

        # 初始化根节点
        self.short_rates[0][0] = (1.0 / np.exp(-self.spot_rates[1] * self.time_steps[1]) - 1.0) / self.time_steps[1]
        self.discount_factors[0][0] = np.exp(-self.spot_rates[1] * self.time_steps[1])
        self.state_prices[0][0] = 1.0
        for i in range(1, n_steps - 1):
            self._calibrate_middle_rate(i)

    def _calibrate_middle_rate(self, i: int) -> None:
        """
        校准第i步的中间利率u(i)
        基于二分法求解满足折现因子d(i,j)的u(i)值
        """
        # 计算目标折现因子 B(i+1)，根据市场即期利率
        # 对应公式: B(i+1) = e^(-R(i+1) * t_(i+1))
        target_discount = np.exp(-self.spot_rates[i + 1] * sum(self.time_steps[:i + 2]))

        # 二分法求解
        u_min, u_max = 1e-4, 0.5
        u_mid = (u_min + u_max) / 2.0
        self.middle_rates[i] = u_mid
        max_iteration = 20
        tolerance = 1e-10  # 收敛容差
        converged = False  # 标记是否收敛
        for _ in range(max_iteration):
            self._generate_short_rates(i)  # 使用当前u_mid计算折现因子
            self._calculate_discount_factors(i)  # 计算折现因子
            self._calculate_state_prices(i)  # 计算状态价格

            # 计算到i+1时刻的零息债券价格 (模型生成的折现因子)
            # 对应公式: sum(Q_(i,j) * d_(i,j))
            calculated_discount = 0.0
            for j in range(-i, i + 2):
                if abs(j) <= i + 1:
                    node_idx = i + j + 1
                    if 0 <= node_idx < len(self.state_prices[i]):
                        calculated_discount += self.discount_factors[i][node_idx] * self.state_prices[i][node_idx]

            # 检查是否收敛
            now_error = abs(calculated_discount - target_discount)
            if now_error < tolerance:
                converged = True
                break

            # 调整u的值(二分查找)
            if calculated_discount > target_discount:
                u_min = u_mid
            else:
                u_max = u_mid

            u_mid = (u_min + u_max) / 2.0
            self.middle_rates[i] = u_mid
        if not converged:
            print(f"警告: 步骤 {i} 的校正在 {max_iteration} 次迭代后未收敛! 最终误差: {now_error:.2e}")

    def _generate_short_rates(self, i: int) -> None:
