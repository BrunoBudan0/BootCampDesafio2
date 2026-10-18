from sqlalchemy import select
from sqlalchemy.orm import joinedload

from models import RiskPolicyGuardrail


class RiskPolicyGuardrailRepository:
    def __init__(self, context) -> None:
        self.session = context.db_session

    def find_all(self) -> list:
        return self.session.scalars(
            select(RiskPolicyGuardrail).options(joinedload(RiskPolicyGuardrail.rule)).order_by(RiskPolicyGuardrail.id)
        ).all()
