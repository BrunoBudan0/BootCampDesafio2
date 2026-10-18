from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from models.base import Base


class RiskPolicyVersion(Base):
    __tablename__ = "risk_policy_version"

    PARAMETER_NAMES = (
        "history_window_days",
        "source_baseline_reference_weight",
        "population_median_reference_weight",
        "reference_average_ticket_individual_to_individual_cents",
        "reference_average_ticket_individual_to_company_cents",
        "reference_average_ticket_company_to_individual_cents",
        "reference_average_ticket_company_to_company_cents",
        "amount_rules_floor_cents",
        "new_account_age_days",
        "new_account_cap_individual_cents",
        "new_account_cap_company_cents",
        "identity_family_cap",
        "velocity_family_cap",
        "amount_family_cap",
        "counterparty_family_cap",
        "counterparty_relationship_cap",
        "behavior_score_cap",
        "two_factor_score_threshold",
        "rejection_score_threshold",
        "two_factor_validity_minutes",
        "destination_risk_alert_threshold",
        "short_term_window_minutes",
    )

    id = Column(Integer, primary_key=True)
    risk_policy_id = Column(Integer, ForeignKey("risk_policy.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    based_on_version_id = Column(Integer, ForeignKey("risk_policy_version.id"))
    change_reason = Column(String(255), nullable=False)
    history_window_days = Column(Integer, nullable=False)
    source_baseline_reference_weight = Column(Integer, nullable=False)
    population_median_reference_weight = Column(Integer, nullable=False)
    reference_average_ticket_individual_to_individual_cents = Column(BigInteger, nullable=False)
    reference_average_ticket_individual_to_company_cents = Column(BigInteger, nullable=False)
    reference_average_ticket_company_to_individual_cents = Column(BigInteger, nullable=False)
    reference_average_ticket_company_to_company_cents = Column(BigInteger, nullable=False)
    amount_rules_floor_cents = Column(BigInteger, nullable=False)
    new_account_age_days = Column(Integer, nullable=False)
    new_account_cap_individual_cents = Column(BigInteger, nullable=False)
    new_account_cap_company_cents = Column(BigInteger, nullable=False)
    identity_family_cap = Column(Integer, nullable=False)
    velocity_family_cap = Column(Integer, nullable=False)
    amount_family_cap = Column(Integer, nullable=False)
    counterparty_family_cap = Column(Integer, nullable=False)
    counterparty_relationship_cap = Column(Integer, nullable=False)
    behavior_score_cap = Column(Integer, nullable=False)
    two_factor_score_threshold = Column(Integer, nullable=False)
    rejection_score_threshold = Column(Integer, nullable=False)
    two_factor_validity_minutes = Column(Integer, nullable=False)
    destination_risk_alert_threshold = Column(Integer, nullable=False)
    short_term_window_minutes = Column(Integer, nullable=False)
    requested_by = Column(String(100))
    risk_acknowledged = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    risk_policy = relationship("RiskPolicy")
    based_on_version = relationship("RiskPolicyVersion", remote_side=[id])
    rule_settings = relationship("RiskPolicyRuleSetting", order_by="RiskPolicyRuleSetting.rule_id")

    def parameters(self) -> dict:
        return {name: getattr(self, name) for name in self.PARAMETER_NAMES}
