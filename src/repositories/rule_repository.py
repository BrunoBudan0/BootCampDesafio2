from sqlalchemy import select

from models import Rule


class RuleRepository:
    def __init__(self, context) -> None:
        self.session = context.db_session

    def find_all_by_name(self) -> dict:
        rules = self.session.scalars(select(Rule).order_by(Rule.id)).all()
        return {rule.name: rule for rule in rules}
