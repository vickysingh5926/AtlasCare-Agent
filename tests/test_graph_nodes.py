"""
Graph Node Unit Tests — Deterministic Nodes

Tests for individual LangGraph nodes in isolation.
Deterministic nodes (regex_router, policy_validation, workflow_planner,
deterministic_executor) require NO LLM calls and run fully synchronously.

Coverage:
  - regex_router: intent classification + entity extraction
  - policy_validation: refund threshold, escalation flag
  - workflow_planner: plan generation, dependency ordering
  - deterministic_executor: tool dispatch, idempotency, partial failure,
    dependency checking, guardrail blocking
"""

import asyncio
import pytest

from agent.state import AgentState, WorkflowStep
from agent.nodes.regex_router import regex_router_node
from agent.nodes.policy_validation import policy_validation_node
from agent.nodes.workflow_planner import workflow_planner_node
from agent.nodes.deterministic_executor import deterministic_executor_node
from agent.nodes.escalation_handler import escalation_handler_node
from guardrails.refund_limit import REFUND_AUTO_LIMIT


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _base_state(**overrides) -> AgentState:
    """Minimal valid AgentState for node testing."""
    state = AgentState(
        session_id="test-session",
        trace_id="test-trace-001",
        customer_id="CUST-001",
        channel="chat",
        user_message="",
        sanitized_message="",
        regex_intent="",
        extracted_intents=[],
        detected_entities={},
        order_ids=[],
        refund_amount=None,
        item_indices=[],
        new_address=None,
        conditions=[],
        actions=[],
        policy_violations=[],
        escalation_required=False,
        escalation_reason="",
        workflow_plan=[],
        current_step=0,
        tool_results=[],
        completed_steps=[],
        failed_steps=[],
        skipped_steps=[],
        executed_ops=[],
        node_latencies={},
        node_transitions=[],
        retry_counts={},
        start_time_ns=0,
        final_response="",
        error_message="",
        workflow_complete=False,
    )
    state.update(overrides)
    return state


# ── regex_router_node tests ───────────────────────────────────────────────────

class TestRegexRouterNode:

    @pytest.mark.asyncio
    async def test_tracking_intent(self):
        state = _base_state(
            sanitized_message="Where is my order ORD-J1?",
        )
        result = await regex_router_node(state)

        assert result["regex_intent"] == "TRACKING"
        assert "ORD-J1" in result["order_ids"]
        assert "regex_router" in result["node_transitions"]
        assert result["node_latencies"]["regex_router"] >= 0

    @pytest.mark.asyncio
    async def test_compound_intent(self):
        state = _base_state(
            sanitized_message="Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address.",
        )
        result = await regex_router_node(state)

        assert result["regex_intent"] == "COMPOUND"
        assert "ORD-J2" in result["order_ids"]
        assert result["item_indices"] == [1]
        assert result["new_address"] is not None
        # The enhanced 'refund me NUMBER' fallback regex captures 85000 even
        # when the generic extract_entities() misses it (re.search hits '2' in ORD-J2 first).
        assert result["refund_amount"] == 85000.0

    @pytest.mark.asyncio
    async def test_policy_intent(self):
        state = _base_state(sanitized_message="What is your return policy?")
        result = await regex_router_node(state)
        assert result["regex_intent"] == "POLICY"

    @pytest.mark.asyncio
    async def test_escalation_intent(self):
        state = _base_state(sanitized_message="I want to speak to a manager.")
        result = await regex_router_node(state)
        assert result["regex_intent"] == "ESCALATION"

    @pytest.mark.asyncio
    async def test_no_order_id(self):
        state = _base_state(sanitized_message="What are your business hours?")
        result = await regex_router_node(state)
        assert result["order_ids"] == []
        assert result["refund_amount"] is None

    @pytest.mark.asyncio
    async def test_node_transitions_appended(self):
        state = _base_state(
            sanitized_message="Track my order ORD-001",
            node_transitions=["previous_node"],
        )
        result = await regex_router_node(state)
        assert result["node_transitions"] == ["previous_node", "regex_router"]


# ── policy_validation_node tests ─────────────────────────────────────────────

class TestPolicyValidationNode:

    @pytest.mark.asyncio
    async def test_refund_above_limit_triggers_escalation(self):
        state = _base_state(
            refund_amount=REFUND_AUTO_LIMIT + 1.0,
            extracted_intents=["COMPOUND"],
        )
        result = await policy_validation_node(state)

        assert result["escalation_required"] is True
        assert len(result["policy_violations"]) > 0
        assert "25,000" in result["escalation_reason"] or "25000" in result["escalation_reason"]

    @pytest.mark.asyncio
    async def test_refund_at_limit_passes(self):
        """Exactly ₹25,000 should NOT trigger escalation (boundary case)."""
        state = _base_state(
            refund_amount=float(REFUND_AUTO_LIMIT),
            extracted_intents=["COMPOUND"],
        )
        result = await policy_validation_node(state)

        assert result["escalation_required"] is False
        assert len(result["policy_violations"]) == 0

    @pytest.mark.asyncio
    async def test_refund_below_limit_passes(self):
        state = _base_state(
            refund_amount=5000.0,
            extracted_intents=["COMPOUND"],
        )
        result = await policy_validation_node(state)

        assert result["escalation_required"] is False
        assert len(result["policy_violations"]) == 0

    @pytest.mark.asyncio
    async def test_no_refund_no_violation(self):
        state = _base_state(
            refund_amount=None,
            extracted_intents=["TRACKING"],
        )
        result = await policy_validation_node(state)

        assert result["escalation_required"] is False
        assert result["policy_violations"] == []

    @pytest.mark.asyncio
    async def test_explicit_escalation_intent_flagged(self):
        state = _base_state(extracted_intents=["ESCALATION"])
        result = await policy_validation_node(state)

        assert result["escalation_required"] is True

    @pytest.mark.asyncio
    async def test_42k_refund_triggers_escalation(self):
        """J3 scenario: ₹42,000 refund should be blocked."""
        state = _base_state(
            refund_amount=42000.0,
            extracted_intents=["COMPOUND"],
        )
        result = await policy_validation_node(state)
        assert result["escalation_required"] is True

    @pytest.mark.asyncio
    async def test_85k_refund_triggers_escalation(self):
        """J2 scenario: ₹85,000 refund should be blocked."""
        state = _base_state(
            refund_amount=85000.0,
            extracted_intents=["COMPOUND"],
        )
        result = await policy_validation_node(state)
        assert result["escalation_required"] is True


# ── workflow_planner_node tests ───────────────────────────────────────────────

class TestWorkflowPlannerNode:

    @pytest.mark.asyncio
    async def test_tracking_plan(self):
        state = _base_state(
            regex_intent="TRACKING",
            extracted_intents=["TRACKING"],
            order_ids=["ORD-J1"],
        )
        result = await workflow_planner_node(state)

        plan = result["workflow_plan"]
        assert len(plan) == 1
        assert plan[0]["tool"] == "oms"
        assert plan[0]["operation"] == "get_order_status"
        assert plan[0]["depends_on"] == []

    @pytest.mark.asyncio
    async def test_compound_plan_ordering(self):
        """Cancel must precede refund in the plan (causal dependency)."""
        state = _base_state(
            regex_intent="COMPOUND",
            extracted_intents=["COMPOUND"],
            order_ids=["ORD-J2"],
            item_indices=[1],
            refund_amount=85000.0,
            new_address="New Address",
            actions=["cancel_item", "initiate_refund", "update_address"],
        )
        result = await workflow_planner_node(state)
        plan = result["workflow_plan"]

        # Find cancel and refund steps
        cancel = next((s for s in plan if s["operation"] == "cancel_line_item"), None)
        refund = next((s for s in plan if s["operation"] == "initiate_refund"), None)
        address = next((s for s in plan if s["operation"] == "update_shipping_address"), None)

        assert cancel is not None, "Cancel step must be in plan"
        assert refund is not None, "Refund step must be in plan"
        assert address is not None, "Address update step must be in plan"

        # Refund must depend on cancel
        assert cancel["step"] in refund["depends_on"], \
            "Refund must depend on cancel step"

        # Address update is independent
        assert address["depends_on"] == [], \
            "Address update should have no dependencies"

    @pytest.mark.asyncio
    async def test_policy_plan(self):
        state = _base_state(
            regex_intent="POLICY",
            extracted_intents=["POLICY"],
            sanitized_message="What is your return policy?",
        )
        result = await workflow_planner_node(state)

        plan = result["workflow_plan"]
        assert len(plan) == 1
        assert plan[0]["tool"] == "kb"
        assert plan[0]["operation"] == "search_policy"

    @pytest.mark.asyncio
    async def test_empty_plan_for_general(self):
        state = _base_state(
            regex_intent="GENERAL",
            extracted_intents=["GENERAL"],
            sanitized_message="Hello there!",
        )
        result = await workflow_planner_node(state)
        assert result["workflow_plan"] == []


# ── deterministic_executor_node tests ────────────────────────────────────────

class TestDeterministicExecutorNode:

    @pytest.mark.asyncio
    async def test_tracking_execution(self):
        """J1: OMS get_order_status succeeds."""
        plan = [WorkflowStep(
            step=1,
            tool="oms",
            operation="get_order_status",
            params={"operation": "get_order_status", "order_id": "ORD-J1"},
            depends_on=[],
        )]
        state = _base_state(workflow_plan=plan)
        result = await deterministic_executor_node(state)

        assert len(result["completed_steps"]) == 1
        assert 1 in result["completed_steps"]
        assert result["failed_steps"] == []
        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["tool"] == "oms"
        assert result["tool_results"][0]["result"] == "success"

    @pytest.mark.asyncio
    async def test_refund_blocked_by_guardrail(self):
        """Payments tool call for >₹25K must be blocked by executor guardrail."""
        plan = [WorkflowStep(
            step=1,
            tool="payments",
            operation="initiate_refund",
            params={"operation": "initiate_refund", "order_id": "ORD-J2", "amount": 85000},
            depends_on=[],
        )]
        state = _base_state(workflow_plan=plan)
        result = await deterministic_executor_node(state)

        # Must be blocked — not in completed_steps
        assert 1 not in result["completed_steps"]
        assert 1 in result["failed_steps"]
        assert result["escalation_required"] is True

        # Tool must NOT appear as a successful "payments" call
        payments_success = [
            tr for tr in result["tool_results"]
            if tr["tool"] == "payments" and tr["result"] == "success"
        ]
        assert len(payments_success) == 0, "Payments tool must not succeed for >₹25K"

    @pytest.mark.asyncio
    async def test_safe_refund_passes_guardrail(self):
        """Payments tool call for ₹5,000 (≤₹25K) must succeed."""
        plan = [WorkflowStep(
            step=1,
            tool="oms",
            operation="get_order_status",
            params={"operation": "get_order_status", "order_id": "ORD-J1"},
            depends_on=[],
        ), WorkflowStep(
            step=2,
            tool="payments",
            operation="initiate_refund",
            params={"operation": "initiate_refund", "order_id": "ORD-J1", "amount": 5000},
            depends_on=[1],
        )]
        state = _base_state(workflow_plan=plan)
        result = await deterministic_executor_node(state)

        assert 2 in result["completed_steps"]
        assert result["escalation_required"] is False

    @pytest.mark.asyncio
    async def test_idempotency_prevents_duplicate(self):
        """Same operation run twice — second execution must be skipped."""
        op_key = "oms:cancel_line_item:ORD-J2:1"
        plan = [WorkflowStep(
            step=1,
            tool="oms",
            operation="cancel_line_item",
            params={"operation": "cancel_line_item", "order_id": "ORD-J2", "item_index": 1},
            depends_on=[],
        )]
        # Pre-populate executed_ops with this key (simulates prior execution)
        state = _base_state(workflow_plan=plan, executed_ops=[op_key])
        result = await deterministic_executor_node(state)

        assert 1 in result["skipped_steps"]
        assert 1 not in result["completed_steps"]
        skipped = [tr for tr in result["tool_results"] if tr["result"] == "skipped"]
        assert len(skipped) == 1

    @pytest.mark.asyncio
    async def test_dependency_failure_skips_dependent(self):
        """Step 2 depends on step 1. Step 1 fails → step 2 must be skipped."""
        plan = [
            WorkflowStep(
                step=1,
                tool="oms",
                operation="cancel_line_item",
                params={"operation": "cancel_line_item", "order_id": "ORD-INVALID-999", "item_index": 1},
                depends_on=[],
            ),
            WorkflowStep(
                step=2,
                tool="payments",
                operation="initiate_refund",
                params={"operation": "initiate_refund", "order_id": "ORD-INVALID-999", "amount": 5000},
                depends_on=[1],  # Depends on step 1 which will fail
            ),
        ]
        state = _base_state(workflow_plan=plan)
        result = await deterministic_executor_node(state)

        assert 1 in result["failed_steps"]
        # Step 2 should be skipped because step 1 failed
        assert 2 in result["skipped_steps"]
        assert 2 not in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_partial_failure_continues(self):
        """
        Partial failure: step 1 fails, step 3 (independent) should still execute.
        Simulates J2: cancel fails, address update still succeeds.
        """
        plan = [
            WorkflowStep(
                step=1,
                tool="oms",
                operation="cancel_line_item",
                params={"operation": "cancel_line_item", "order_id": "ORD-INVALID-999", "item_index": 1},
                depends_on=[],
            ),
            WorkflowStep(
                step=2,
                tool="oms",
                operation="update_shipping_address",
                params={"operation": "update_shipping_address", "order_id": "ORD-J2", "new_address": "123 New St"},
                depends_on=[],  # Independent — no dependency on step 1
            ),
        ]
        state = _base_state(workflow_plan=plan)
        result = await deterministic_executor_node(state)

        # Step 1 fails, step 2 succeeds independently
        assert 1 in result["failed_steps"]
        assert 2 in result["completed_steps"]
        assert len(result["tool_results"]) == 2


# ── escalation_handler_node tests ────────────────────────────────────────────

class TestEscalationHandlerNode:

    @pytest.mark.asyncio
    async def test_crm_case_created_with_trace_id(self):
        """CRM case must include trace_id for audit linkage."""
        state = _base_state(
            escalation_required=True,
            escalation_reason="Refund ₹42,000 exceeds auto-limit ₹25,000",
            customer_id="CUST-001",
        )
        result = await escalation_handler_node(state)

        tool_results = result["tool_results"]
        crm_calls = [tr for tr in tool_results if tr["tool"] == "crm"]
        assert len(crm_calls) == 1, "Exactly one CRM case must be created"

        crm_params = crm_calls[0]["params"]
        assert crm_params.get("trace_id") == "test-trace-001", \
            "CRM case must include trace_id for audit linkage"
        assert crm_calls[0]["result"] == "success"

    @pytest.mark.asyncio
    async def test_crm_case_summary_not_empty(self):
        state = _base_state(
            escalation_required=True,
            escalation_reason="Test escalation reason",
        )
        result = await escalation_handler_node(state)

        crm_calls = [tr for tr in result["tool_results"] if tr["tool"] == "crm"]
        assert len(crm_calls[0]["params"]["summary"]) > 0
