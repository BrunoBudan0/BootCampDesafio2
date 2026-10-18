from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from models.base import Base


class RiskPolicyGuardrail(Base):
    __tablename__ = "risk_policy_guardrail"

    id = Column(Integer, primary_key=True)
    parameter_name = Column(String(80))
    rule_id = Column(Integer, ForeignKey("rule.id"))
    setting_field = Column(String(20))
    loosening_direction = Column(String(10), nullable=False)
    refusal_limit = Column(Numeric(14, 2))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rule = relationship("Rule")

    @property
    def setting_name(self) -> str:
        if self.parameter_name is not None:
            return self.parameter_name

        return f"{self.rule.code}.{self.setting_field}"

    def value_in(self, version):
        if self.parameter_name is not None:
            return getattr(version, self.parameter_name)

        for setting in version.rule_settings:
            if setting.rule.code == self.rule.code:
                return getattr(setting, self.setting_field)

        return None
