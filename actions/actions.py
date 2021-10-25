# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions


# This is a simple example for a custom action which utters "Hello World!"

from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.types import DomainDict
from rasa_sdk.forms import FormAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import utils
from rasa_sdk.events import UserUtteranceReverted, AllSlotsReset, SlotSet, EventType, \
    ActiveLoop, Restarted, SessionStarted, ActionExecuted
import logging
import yaml
import os

logger = logging.getLogger(__name__)
REQUESTED_SLOT = "requested_slot"


# 自定义动作，重置对话系统
class ActionResetSlot(Action):
    def name(self) -> Text:
        return "action_reset_slot"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        # return [AllSlotsReset()]
        return [Restarted()]


# 自定义动作，对槽位进行追问
class AskForSlot(Action):
    def name(self) -> Text:
        return "action_ask_slot"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        slot = tracker.get_slot(REQUESTED_SLOT)
        message = tracker.latest_message()
        # dispatcher.utter_message(template=f"utter_ask_{slot}", **tracker.slots)
        return [SlotSet(REQUESTED_SLOT, slot)]


# 自定义动作，对槽位设置值
class SetSlot(Action):
    def name(self) -> Text:
        return "action_set_slot"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        # slot = tracker.get_slot(REQUESTED_SLOT)
        res = []
        entities = tracker.latest_message["entities"]
        print(entities)
        for entity in entities:
            slot_name, slot_val = entity["entity"], entity["value"]
            res.append(SlotSet(slot_name, slot_val))
        # dispatcher.utter_message(template=f"utter_ask_{slot}", **tracker.slots)
        # return [SlotSet(REQUESTED_SLOT, slot)]
        return res


