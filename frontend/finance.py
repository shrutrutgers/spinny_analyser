"""Loan amortization helpers used by the Streamlit dashboard."""
from __future__ import annotations


def monthly_emi(principal: float, annual_rate_pct: float, tenure_months: int) -> float:
    if principal <= 0 or tenure_months <= 0:
        return 0.0
    if annual_rate_pct <= 0:
        return principal / tenure_months
    r = annual_rate_pct / 12 / 100
    factor = (1 + r) ** tenure_months
    return principal * r * factor / (factor - 1)


def remaining_balance(
    principal: float, annual_rate_pct: float, tenure_months: int, months_paid: int
) -> float:
    """Outstanding principal after `months_paid` EMIs on an amortizing loan."""
    if months_paid <= 0:
        return principal
    if months_paid >= tenure_months:
        return 0.0
    if annual_rate_pct <= 0:
        emi = principal / tenure_months
        return max(principal - emi * months_paid, 0.0)
    r = annual_rate_pct / 12 / 100
    emi = monthly_emi(principal, annual_rate_pct, tenure_months)
    balance = principal * (1 + r) ** months_paid - emi * (((1 + r) ** months_paid - 1) / r)
    return max(balance, 0.0)
