"""
Flow Manager - Deterministik akış kontrol
LLM'siz, pure logic ile next action'ı belirler
"""

import logging
from typing import Dict, Any, Optional, List
from .flows import (
    FlowType, ActionType, StateMarker,
    get_required_fields, get_missing_message,
    get_booking_confirmation_message, get_cancel_confirmation_message
)


class FlowManager:
    """
    Deterministik flow yönetimi.

    Görevler:
    1. Hangi field'lar eksik? → Ask missing
    2. Tool çağırma zamanı geldi mi? → Tool call
    3. Onay alınmalı mı? → Confirm
    4. Tüm işlem bitti mi? → Final action

    LLM kullanmaz, sadece if-else logic.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_next_action(
        self,
        intent: str,
        collected: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Mevcut state'e göre next action'ı belirle.

        Args:
            intent: User intent (booking, cancel, query, chat)
            collected: Toplanan bilgiler (phone, service, date, time, ...)
            context: Konuşma context'i (customer_name, state markers, ...)

        Returns:
            Action dict: {
                "action": "ask_missing" | "tool_call" | "confirm" | "chat",
                "field": "phone",  # if ask_missing
                "message": "...",
                "tool": "check_customer",  # if tool_call
                "tool_params": {...}
            }
        """
        self.logger.info(f"🔄 Flow Manager: Intent={intent}, Collected keys={list(collected.keys())}")

        # Intent'e göre flow'a yönlendir
        if intent == FlowType.BOOKING:
            return self._check_booking_flow(collected, context)

        elif intent == FlowType.CANCEL:
            return self._check_cancel_flow(collected, context)

        elif intent == FlowType.QUERY:
            return self._check_query_flow(collected, context)

        elif intent == FlowType.CAMPAIGN_INQUIRY:
            # Kampanya sorgusu - direkt tool call
            return self._build_action(
                action_type=ActionType.TOOL_CALL,
                tool="check_campaigns",
                tool_params={"customer_phone": collected.get("phone")}
            )

        else:
            # Chat - LLM #2'ye bırak
            return self._build_action(ActionType.CHAT)

    # ========================================================================
    # BOOKING FLOW
    # ========================================================================

    def _check_booking_flow(self, collected: Dict, context: Dict) -> Dict:
        """
        Randevu oluşturma akışı (step-by-step)

        Steps:
        1. Phone sor
        2. check_customer (tool)
        3. Service sor
        4. Expert sor (veya list_experts)
        5. Date/Time sor
        6. check_availability (tool)
        7. Handle unavailable (alternative sor)
        8. Confirm
        9. create_appointment (tool)
        """

        # STEP 1: Phone kontrolü
        if not collected.get("phone"):
            return self._build_action(
                action_type=ActionType.ASK_MISSING,
                field="phone",
                message=get_missing_message("phone")
            )

        # STEP 2: Customer check (tool call)
        if not context.get(StateMarker.CUSTOMER_CHECKED):
            return self._build_action(
                action_type=ActionType.TOOL_CALL,
                tool="check_customer",
                tool_params={"phone": collected["phone"]}
            )

        # STEP 3: Service kontrolü
        if not collected.get("service"):
            return self._build_action(
                action_type=ActionType.ASK_MISSING,
                field="service",
                message=get_missing_message("service")
            )

        # STEP 4: Expert kontrolü
        if not collected.get("expert_name"):
            # Eğer experts listelenmemişse, liste (tool)
            if not context.get(StateMarker.EXPERTS_LISTED):
                return self._build_action(
                    action_type=ActionType.TOOL_CALL,
                    tool="list_experts",
                    tool_params={"service_type": collected["service"]}
                )
            # Liste gösterildi ama seçim yapılmadı, tekrar sor
            return self._build_action(
                action_type=ActionType.ASK_MISSING,
                field="expert_name",
                message="Hangi uzmanımızdan randevu almak istersiniz?"
            )

        # STEP 5: Date kontrolü
        if not collected.get("date"):
            return self._build_action(
                action_type=ActionType.ASK_MISSING,
                field="date",
                message=get_missing_message("date")
            )

        # STEP 6: Time kontrolü
        if not collected.get("time"):
            return self._build_action(
                action_type=ActionType.ASK_MISSING,
                field="time",
                message=get_missing_message("time")
            )

        # STEP 7: Availability check (tool call)
        if not context.get(StateMarker.AVAILABILITY_CHECKED):
            return self._build_action(
                action_type=ActionType.TOOL_CALL,
                tool="check_availability",
                tool_params={
                    "service_type": collected["service"],
                    "date_time": f"{collected['date']}T{collected['time']}:00",
                    "expert_name": collected["expert_name"]
                }
            )

        # STEP 8: Handle unavailability
        if context.get(StateMarker.AVAILABILITY_CHECKED):
            is_available = context.get(StateMarker.AVAILABLE)

            if not is_available:
                # Müsait değil - alternative gösterildi mi?
                if not context.get(StateMarker.ALTERNATIVES_SHOWN):
                    # Alternative sor
                    return self._build_action(
                        action_type=ActionType.ASK_ALTERNATIVE,
                        message="Bu saat dolu. Alternatif saatler önerelim mi?"
                    )
                else:
                    # Alternative gösterildi ama user seçim yapmadı
                    # LLM #2'ye bırak (user "hayır" demiş olabilir)
                    return self._build_action(ActionType.CHAT)

        # STEP 9: Confirm
        if context.get(StateMarker.AVAILABLE) and not context.get(StateMarker.CONFIRMED):
            return self._build_action(
                action_type=ActionType.CONFIRM,
                message=get_booking_confirmation_message(collected)
            )

        # STEP 10: Create appointment (tool call)
        if context.get(StateMarker.CONFIRMED):
            return self._build_action(
                action_type=ActionType.TOOL_CALL,
                tool="create_appointment",
                tool_params={
                    "customer_phone": collected["phone"],
                    "service_type": collected["service"],
                    "appointment_datetime": f"{collected['date']}T{collected['time']}:00",
                    "expert_name": collected["expert_name"]
                }
            )

        # Fallback - bu noktaya normalde gelmemeli
        self.logger.warning("⚠️ Booking flow unexpected state")
        return self._build_action(ActionType.CHAT)

    # ========================================================================
    # CANCEL FLOW
    # ========================================================================

    def _check_cancel_flow(self, collected: Dict, context: Dict) -> Dict:
        """
        Randevu iptal akışı

        Steps:
        1. Phone sor
        2. get_customer_appointments (tool)
        3. Confirm cancel
        4. cancel_appointment (tool)
        """

        # STEP 1: Phone kontrolü
        if not collected.get("phone"):
            return self._build_action(
                action_type=ActionType.ASK_MISSING,
                field="phone",
                message=get_missing_message("phone")
            )

        # STEP 2: Get appointments (tool)
        if not context.get(StateMarker.APPOINTMENTS_FETCHED):
            return self._build_action(
                action_type=ActionType.TOOL_CALL,
                tool="get_customer_appointments",
                tool_params={"phone": collected["phone"]}
            )

        # STEP 3: Confirm cancel
        if context.get(StateMarker.APPOINTMENTS_FETCHED) and not context.get(StateMarker.CONFIRMED):
            # En son randevuyu iptal etmek için onay iste
            latest_appointment = context.get("latest_appointment")
            return self._build_action(
                action_type=ActionType.CONFIRM,
                message=get_cancel_confirmation_message(collected, latest_appointment)
            )

        # STEP 4: Cancel appointment (tool)
        if context.get(StateMarker.CONFIRMED):
            return self._build_action(
                action_type=ActionType.TOOL_CALL,
                tool="cancel_appointment",
                tool_params={
                    "phone": collected["phone"],
                    "appointment_code": context.get("appointment_code")
                }
            )

        # Fallback
        return self._build_action(ActionType.CHAT)

    # ========================================================================
    # QUERY FLOW
    # ========================================================================

    def _check_query_flow(self, collected: Dict, context: Dict) -> Dict:
        """
        Randevu sorgulama akışı

        Steps:
        1. Phone sor
        2. get_customer_appointments (tool)
        """

        # STEP 1: Phone kontrolü
        if not collected.get("phone"):
            return self._build_action(
                action_type=ActionType.ASK_MISSING,
                field="phone",
                message=get_missing_message("phone")
            )

        # STEP 2: Get appointments (tool)
        # Query için tekrar fetching'e gerek yok, direkt çağır
        return self._build_action(
            action_type=ActionType.TOOL_CALL,
            tool="get_customer_appointments",
            tool_params={"phone": collected["phone"]}
        )

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _build_action(
        self,
        action_type: ActionType,
        field: Optional[str] = None,
        message: Optional[str] = None,
        tool: Optional[str] = None,
        tool_params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Action dict builder (standardization)

        Returns:
            {
                "action": "ask_missing" | "tool_call" | "confirm" | "chat",
                "field": "phone",
                "message": "...",
                "tool": "check_customer",
                "tool_params": {...}
            }
        """
        action = {
            "action": action_type.value
        }

        if field:
            action["field"] = field

        if message:
            action["message"] = message

        if tool:
            action["tool"] = tool
            action["tool_params"] = tool_params or {}

        self.logger.debug(f"📤 Next action: {action['action']}")
        return action

    def reset_availability_check(self, context: Dict):
        """
        Availability check'i sıfırla (user date/time değiştirdiyse)
        """
        context[StateMarker.AVAILABILITY_CHECKED] = False
        context[StateMarker.AVAILABLE] = False
        context[StateMarker.ALTERNATIVES_SHOWN] = False
        self.logger.info("♻️ Availability check reset")


# ============================================================================
# TEST & VALIDATION
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("\n" + "="*50)
    print("FLOW MANAGER - LOGIC TEST")
    print("="*50 + "\n")

    manager = FlowManager()

    # Test case 1: Booking - Phone eksik
    collected = {}
    context = {}
    action = manager.get_next_action("booking", collected, context)
    print(f"Test 1: {action}")
    assert action["action"] == "ask_missing"
    assert action["field"] == "phone"
    print("✅ Passed\n")

    # Test case 2: Booking - Phone var, customer check gerekli
    collected = {"phone": "05321234567"}
    context = {}
    action = manager.get_next_action("booking", collected, context)
    print(f"Test 2: {action}")
    assert action["action"] == "tool_call"
    assert action["tool"] == "check_customer"
    print("✅ Passed\n")

    # Test case 3: Booking - Customer checked, service eksik
    collected = {"phone": "05321234567"}
    context = {StateMarker.CUSTOMER_CHECKED: True}
    action = manager.get_next_action("booking", collected, context)
    print(f"Test 3: {action}")
    assert action["action"] == "ask_missing"
    assert action["field"] == "service"
    print("✅ Passed\n")

    print("="*50)
    print("ALL TESTS PASSED ✅")
    print("="*50)
