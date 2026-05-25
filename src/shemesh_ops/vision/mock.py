"""Mock vision extractor — returns generic placeholder values.

This backend exists so the pipeline + UI can run end-to-end without a real
vision model (no GPU required). Values are synthetic, not from any real
person. For real client data, use a real backend like OllamaVisionExtractor.

To extend with more test scenarios, add task_name entries to _RESPONSES or
implement a different backend.
"""
from __future__ import annotations

from .base import VisionExtractor

_RESPONSES: dict[str, dict] = {
    "id_card": {
        "full_name": "ישראל ישראלי",
        "first_name": "ישראל",
        "last_name": "ישראלי",
        "id_number": "999999999",
        "date_of_birth": "1980-01-01",
        "issue_date": "2020-01-01",
        "expiry_date": "2030-01-01",
        "father_name": "אבא",
        "mother_name": "אמא",
        "grandfather_name": "סבא",
        "place_of_birth": "ישראל",
        "card_number": "000000000",
        "sex": "זכר",
        "citizenship": "אזרחות ישראלית",
    },
    "bank_labels": {
        "holder_name": "ישראלי ישראל",
        "address": "רחוב הדוגמה 1, עיר",
    },
    "tagmulim_labels": [
        {"kupa_name": "קרן פנסיה דוגמה א", "member_status": "עצמאי"},
        {"kupa_name": "קרן פנסיה דוגמה א", "member_status": "שכיר"},
        {"kupa_name": "קרן פנסיה דוגמה ב", "member_status": "שכיר"},
    ],
    "pitsuyim_labels": [
        {"kupa_name": "קרן פנסיה דוגמה ב", "employer_name": "ישראלי ישראל"},
        {"kupa_name": "קרן פנסיה דוגמה ב", "employer_name": "מעסיק דוגמה א"},
        {"kupa_name": "קרן פנסיה דוגמה ב", "employer_name": "מעסיק דוגמה ב"},
        {"kupa_name": "קרן פנסיה דוגמה א", "employer_name": "מעסיק עצמאי"},
        {"kupa_name": "קרן פנסיה דוגמה א", "employer_name": "מעסיק דוגמה ג"},
        {"kupa_name": "קרן פנסיה דוגמה א", "employer_name": "מעסיק דוגמה ד"},
        {"kupa_name": "קרן פנסיה דוגמה ב", "employer_name": "מעסיק דוגמה ה"},
    ],
    "maslaka_labels": [
        {"management_company": "חברה דוגמה א", "status": "לא פעיל", "product_type_label": "פנסיה ותיקה יסודי"},
        {"management_company": "חברה דוגמה א", "status": "לא פעיל", "product_type_label": "פנסיה ותיקה יסודי"},
        {"management_company": "חברה דוגמה א", "status": "לא פעיל", "product_type_label": "פנסיה ותיקה יסודי"},
        {"management_company": "חברה דוגמה ב", "status": "פעיל", "product_type_label": "פנסיה חדשה מקיפה"},
        {"management_company": "חברה דוגמה ב", "status": "פעיל", "product_type_label": "פוליסת סיכון טהור"},
        {"management_company": "חברה דוגמה ג", "status": "פעיל", "product_type_label": "פוליסת סיכון טהור"},
        {"management_company": "חברה דוגמה ב", "status": "פעיל", "product_type_label": "קרן השתלמות"},
        {"management_company": "חברה דוגמה ב", "status": "פעיל", "product_type_label": "קרן השתלמות"},
    ],
    "bl_periods_labels": [
        {"occupation": "עובד", "employer_label": "מעסיק דוגמה א"},
    ],
    "bl_employer_details_labels": [
        ("90000000001", "מעסיק דוגמה א", "כתובת דוגמה 1"),
        ("90000000002", "מעסיק דוגמה ב", "כתובת דוגמה 2"),
    ],
    # Model-review gate: mock returns "no issues" so tests stay deterministic.
    "form_review": {"findings": []},
}


class MockVisionExtractor(VisionExtractor):
    """Returns synthetic placeholder responses.

    Look up by `task_name`. Raises if the task is unknown — there's no
    silent fallback, because a missing label in production would silently
    corrupt the form.
    """

    def extract(
        self,
        images: list[bytes],
        instruction: str,
        task_name: str = "",
    ) -> dict:
        if not task_name:
            raise ValueError("MockVisionExtractor requires task_name")
        if task_name not in _RESPONSES:
            raise KeyError(
                f"Mock has no canned response for task {task_name!r}. "
                "Either add one in vision/mock.py or use a real backend."
            )
        value = _RESPONSES[task_name]
        if isinstance(value, list):
            return {"items": value}
        return value
