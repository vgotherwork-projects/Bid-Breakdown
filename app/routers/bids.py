from fastapi import APIRouter

from ..bid_schemas import EmployeeBidBreakdown, EmployeeBidInput
from ..calculator import calculate_employee_bid

router = APIRouter(prefix="/bids", tags=["bids"])


@router.post("/calculate", response_model=EmployeeBidBreakdown)
def calculate(bid: EmployeeBidInput) -> EmployeeBidBreakdown:
    """Compute an employee CTC cost breakdown (monthly + annual) with PTO and gratuity."""
    return calculate_employee_bid(bid)
