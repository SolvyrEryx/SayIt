"""Persistent, scheduled desktop reminders for SayIt.

Local-first and LLM-optional: reminder creation, scheduling and notification all
work on-device without any cloud/API. This package is deliberately separate from
conversation history — disabling chat retention never deletes real reminders.

Nothing here performs shell/filesystem/autonomous actions.
"""

from .model import (
    Reminder,
    ReminderError,
    ReminderRevision,
    ReminderStatus,
    build_trigger,
)
from .store import ReminderStore
from .notifier import (
    FakeNotifier,
    NotificationResult,
    Notifier,
    NullNotifier,
    TrayNotifier,
    WindowsToastNotifier,
    build_notifier,
)
from .scheduler import FireOutcome, ReminderScheduler, SchedulerCore
from .service import ReminderService, ScheduleResult
from .bridge import BridgeReply, ReminderConversationBridge

__all__ = [
    "Reminder",
    "ReminderError",
    "ReminderRevision",
    "ReminderStatus",
    "build_trigger",
    "ReminderStore",
    "Notifier",
    "NotificationResult",
    "FakeNotifier",
    "NullNotifier",
    "TrayNotifier",
    "WindowsToastNotifier",
    "build_notifier",
    "SchedulerCore",
    "ReminderScheduler",
    "FireOutcome",
    "ReminderService",
    "ScheduleResult",
    "ReminderConversationBridge",
    "BridgeReply",
]
