"""兼容导出层：finance_agent 现已直接复用 planner 作为 supervisor。"""

from app.agents.components.finance_agent.planner.node import (
    route_after_supervisor,
    supervisor_node as finance_agent_supervisor,
)
