"""服务容器，负责实例化和组织核心服务。"""

from __future__ import annotations

from dataclasses import dataclass

from steward.connectors.registry import ConnectorRegistry
from steward.core.config import Settings
from steward.core.policy import PolicyLoader
from steward.learning.feedback import FeedbackLearningService
from steward.planning import PlanCompiler, SuperpowersAssets
from steward.runtime.execution.dispatcher import ExecutionDispatcher
from steward.services.action_runner import ActionRunnerService
from steward.services.brief_preferences import BriefPreferenceService
from steward.services.briefing import BriefingService
from steward.services.capability_manager import CapabilityManagerService
from steward.services.conflict import ConflictService
from steward.services.context_space import ContextSpaceService
from steward.services.dashboard import DashboardService
from steward.services.decision_log import DecisionLogService
from steward.services.event_ingest import EventIngestService
from steward.services.execution_agent import ExecutionAgent
from steward.services.integration_config import IntegrationConfigService
from steward.services.memory_manager import MemoryManager
from steward.services.model_gateway import ModelGateway
from steward.services.plan_control import PlanControlService
from steward.services.planner import PlannerService
from steward.services.policy_gate import PolicyGateService
from steward.services.recorder_agent import RecorderAgent
from steward.services.tool_registry import ToolRegistry
from steward.services.verifier import VerifierService
from steward.services.waiting import WaitingService


@dataclass(slots=True)
class ServiceContainer:
    """应用服务容器。"""

    settings: Settings
    policy_loader: PolicyLoader
    connectors: ConnectorRegistry
    model_gateway: ModelGateway
    context_space_service: ContextSpaceService
    planner_service: PlannerService
    policy_gate_service: PolicyGateService
    decision_log_service: DecisionLogService
    verifier_service: VerifierService
    action_runner_service: ActionRunnerService
    waiting_service: WaitingService
    conflict_service: ConflictService
    briefing_service: BriefingService
    brief_preference_service: BriefPreferenceService
    feedback_service: FeedbackLearningService
    capability_manager_service: CapabilityManagerService
    dashboard_service: DashboardService
    event_ingest_service: EventIngestService
    plan_control_service: PlanControlService
    integration_config_service: IntegrationConfigService
    memory_manager: MemoryManager
    recorder_agent: RecorderAgent
    tool_registry: ToolRegistry
    execution_agent: ExecutionAgent


def build_service_container(settings: Settings) -> ServiceContainer:
    """创建服务容器。"""
    policy_loader = PolicyLoader(settings.policy_path)
    model_gateway = ModelGateway(settings)
    integration_config_service = IntegrationConfigService(settings, model_gateway)
    integration_config_service.load_runtime_overrides()
    brief_preference_service = BriefPreferenceService(settings)
    brief_preference_service.load_runtime_overrides()
    connectors = ConnectorRegistry(settings)

    context_space_service = ContextSpaceService(model_gateway)
    superpowers_assets = SuperpowersAssets.load()
    planner_service = PlannerService(
        plan_compiler=PlanCompiler(
            writing_guidance=superpowers_assets.writing_plans,
            executing_guidance=superpowers_assets.executing_plans,
        ),
        model_gateway=model_gateway,
        workspace_dir=".",
    )
    policy_gate_service = PolicyGateService(settings, policy_loader)
    decision_log_service = DecisionLogService()
    verifier_service = VerifierService()
    execution_dispatcher = ExecutionDispatcher()
    action_runner_service = ActionRunnerService(
        connectors,
        decision_log_service,
        execution_dispatcher,
        execution_enabled=settings.execution_enabled,
    )
    waiting_service = WaitingService(action_runner_service)
    conflict_service = ConflictService()
    briefing_service = BriefingService(model_gateway)
    feedback_service = FeedbackLearningService()
    capability_manager_service = CapabilityManagerService(integration_config_service, connectors)
    dashboard_service = DashboardService(connectors, model_gateway)

    event_ingest_service = EventIngestService(
        context_space_service=context_space_service,
        planner_service=planner_service,
        policy_gate_service=policy_gate_service,
        action_runner_service=action_runner_service,
        conflict_service=conflict_service,
        waiting_service=waiting_service,
    )
    plan_control_service = PlanControlService(
        action_runner_service=action_runner_service,
        policy_gate_service=policy_gate_service,
        feedback_service=feedback_service,
    )

    memory_manager = MemoryManager(brain_dir=settings.brain_dir)
    memory_manager.ensure_structure()
    recorder_agent = RecorderAgent(memory_manager)

    tool_registry = ToolRegistry(
        integration_config=integration_config_service,
        workspace_dir=".",
    )
    execution_agent = ExecutionAgent(tool_registry=tool_registry, settings=settings)

    return ServiceContainer(
        settings=settings,
        policy_loader=policy_loader,
        connectors=connectors,
        model_gateway=model_gateway,
        context_space_service=context_space_service,
        planner_service=planner_service,
        policy_gate_service=policy_gate_service,
        decision_log_service=decision_log_service,
        verifier_service=verifier_service,
        action_runner_service=action_runner_service,
        waiting_service=waiting_service,
        conflict_service=conflict_service,
        briefing_service=briefing_service,
        brief_preference_service=brief_preference_service,
        feedback_service=feedback_service,
        capability_manager_service=capability_manager_service,
        dashboard_service=dashboard_service,
        event_ingest_service=event_ingest_service,
        plan_control_service=plan_control_service,
        integration_config_service=integration_config_service,
        memory_manager=memory_manager,
        recorder_agent=recorder_agent,
        tool_registry=tool_registry,
        execution_agent=execution_agent,
    )
