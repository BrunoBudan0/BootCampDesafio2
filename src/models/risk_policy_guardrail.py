from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from models.base import Base


class RiskPolicyGuardrail(Base):
    __tablename__ = "risk_policy_guardrail"

    id = Column(Integer, primary_key=True)
    policy_parameter_name = Column(String(80))
    rule_id = Column(Integer, ForeignKey("rule.id"))
    rule_setting_field = Column(String(20))
    loosening_direction = Column(String(10), nullable=False)
    loosest_accepted_value = Column(Numeric(14, 2))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rule = relationship("Rule")

    @property
    def setting_name(self) -> str:
        if self.policy_parameter_name is not None:
            return self.policy_parameter_name

        return f"{self.rule.name}.{self.rule_setting_field}"

    def value_in(self, version):
        if self.policy_parameter_name is not None:
            return getattr(version, self.policy_parameter_name)

        for setting in version.rule_settings:
            if setting.rule.name == self.rule.name:
                return getattr(setting, self.rule_setting_field)

        return None
