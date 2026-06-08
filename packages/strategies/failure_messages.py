FAILURE_MESSAGES_ZH = {
    "basis_not_enough_after_costs": "扣除费用和滑点后，basis 收益不足。",
    "capacity_below_target_notional": "订单簿容量低于目标名义金额。",
    "funding_not_enough_after_costs": "扣除对冲成本后，funding 收益不足。",
    "non_positive_after_fees_and_slippage": "扣除费用和滑点后，净 edge 不为正。",
    "requires_expiry_and_borrow_checks_before_execution": "执行前需要检查交割日、借币和资金占用。",
    "requires_spot_or_correlated_hedge_before_execution": "执行前需要现货或相关资产对冲腿。",
    "reserved_strategy_not_implemented": "该策略接口已预留，但当前版本尚未实现。",
}


def failure_message_zh(code: str) -> str:
    return FAILURE_MESSAGES_ZH.get(code, code)
