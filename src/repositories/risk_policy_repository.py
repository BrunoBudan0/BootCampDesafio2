from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from models import RiskPolicy, RiskPolicyRuleSetting, RiskPolicyVersion

class RiskPolicyRepository:
    def __init__(self, context) -> None:
        self.session = context.db_session

    def find_current_version(self, policy_name: str) -> RiskPolicyVersion:
        latest_version = (
            select(func.max(RiskPolicyVersion.version))
            .join(RiskPolicy)
            .where(RiskPolicy.name == policy_name)
            .scalar_subquery()
        )
        return self.session.scalars(
            self.select_complete_version()
            .where(RiskPolicy.name == policy_name, RiskPolicyVersion.version == latest_version)
        ).one()

    def find_version(self, policy_name: str, version: int) -> Optional[RiskPolicyVersion]:
        return self.session.scalars(
            self.select_complete_version()
            .where(RiskPolicy.name == policy_name, RiskPolicyVersion.version == version)
        ).one_or_none()

    def find_current_versions_of_kind(self, policy_kind: str) -> list:
        latest_version_per_policy = (
            select(RiskPolicyVersion.risk_policy_id, func.max(RiskPolicyVersion.version).label("version"))
            .group_by(RiskPolicyVersion.risk_policy_id)
            .subquery()
        )
        return self.session.scalars(
            self.select_complete_version()
            .join(
                latest_version_per_policy,
                (latest_version_per_policy.c.risk_policy_id == RiskPolicyVersion.risk_policy_id)
                & (latest_version_per_policy.c.version == RiskPolicyVersion.version),
            )
            .where(RiskPolicy.kind == policy_kind)
            .order_by(RiskPolicy.id)
        ).all()

    def add_version(self, version: RiskPolicyVersion) -> None:
        self.session.add(version)
        self.session.flush()

    @staticmethod
    def select_complete_version():
        return (
            select(RiskPolicyVersion)
            .join(RiskPolicy, RiskPolicy.id == RiskPolicyVersion.risk_policy_id)
            .options(
                joinedload(RiskPolicyVersion.risk_policy),
                joinedload(RiskPolicyVersion.based_on_version).joinedload(RiskPolicyVersion.risk_policy),
                selectinload(RiskPolicyVersion.rule_settings).joinedload(RiskPolicyRuleSetting.rule),
            )
        )
