"""Mock vision extractor — returns hardcoded values for the example customer
(אורי בן פורת, ID 029742590).

Use for tests, demos, and any time you want the pipeline to run end-to-end
without a real vision model installed. To work with a different customer,
implement a real backend (e.g., OllamaVisionExtractor) instead of extending
this mock.

All values below were extracted manually by visually reading the rendered
PDFs and JPEGs in this project's fixture folder.
"""
from __future__ import annotations

from .base import VisionExtractor

_RESPONSES: dict[str, dict] = {
    "id_card": {
        "full_name": "אורי בן פורת",
        "first_name": "אורי",
        "last_name": "בן פורת",
        "id_number": "029742590",
        "date_of_birth": "1973-02-15",
        "issue_date": "2022-09-07",
        "expiry_date": "2032-09-04",
        "father_name": "יוסף",
        "mother_name": "מיכל",
        "grandfather_name": "ראובן",
        "place_of_birth": "ישראל",
        "card_number": "011310248",
        "sex": "זכר",
        "citizenship": "אזרחות ישראלית",
    },
    "bank_labels": {
        "holder_name": "בן פורת אורי",
        "address": "הפרדס 8, מולדת",
    },
    "tagmulim_labels": [
        {"kupa_name": "קרן הפנסיה עתודות", "member_status": "עצמאי"},
        {"kupa_name": "קרן הפנסיה עתודות", "member_status": "שכיר"},
        {"kupa_name": "מגדל מקפת אישית", "member_status": "שכיר"},
    ],
    "pitsuyim_labels": [
        {"kupa_name": "מגדל מקפת אישית", "employer_name": "בן פורת אורי"},
        {"kupa_name": "מגדל מקפת אישית", "employer_name": "מולדת כפר בני ברית"},
        {"kupa_name": "מגדל מקפת אישית", "employer_name": "רימון פיתוח וכבישים בעמ"},
        {"kupa_name": "קרן הפנסיה עתודות", "employer_name": "מעסיק עצמאי"},
        {"kupa_name": "קרן הפנסיה עתודות", "employer_name": "טל-נטפים ברמה בע\"מ"},
        {"kupa_name": "קרן הפנסיה עתודות", "employer_name": "עתודות הוותיקה - חברה מנהלת"},
        {"kupa_name": "מגדל מקפת אישית", "employer_name": "אמבורגריה בעמ"},
    ],
    "maslaka_labels": [
        # Page 3 — 3 funds at עתודות
        {"management_company": "עתודות", "status": "לא פעיל", "product_type_label": "פנסיה ותיקה יסודי"},
        {"management_company": "עתודות", "status": "לא פעיל", "product_type_label": "פנסיה ותיקה יסודי"},
        {"management_company": "עתודות", "status": "לא פעיל", "product_type_label": "פנסיה ותיקה יסודי"},
        # Page 4 — מגדל פנסיה חדשה
        {"management_company": "מגדל", "status": "פעיל", "product_type_label": "פנסיה חדשה מקיפה"},
        # Page 5 — 2 risk policies (מגדל + הראל)
        {"management_company": "מגדל", "status": "פעיל", "product_type_label": "פוליסת סיכון טהור"},
        {"management_company": "הראל", "status": "פעיל", "product_type_label": "פוליסת סיכון טהור"},
        # Page 6 — 2 קה"ש at מגדל
        {"management_company": "מגדל מקפת - לאומי", "status": "פעיל", "product_type_label": "קרן השתלמות"},
        {"management_company": "מגדל מקפת - לאומי", "status": "פעיל", "product_type_label": "קרן השתלמות"},
    ],
    "bl_periods_labels": [
        {"occupation": "חבר קיבוץ", "employer_label": "קבוץ תל קציר / חברים"},
        {"occupation": "עובד", "employer_label": "שטרית את שמואל-עב' ביוב וני"},
        {"occupation": "חבר קיבוץ", "employer_label": "קבוץ תל קציר / חברים"},
        {"occupation": "עובד", "employer_label": "קבוץ מיצר / חברים"},
        {"occupation": "חבר קיבוץ", "employer_label": "קבוץ תל קציר / חברים"},
        {"occupation": "עובד", "employer_label": "גמר,הראל וקורן/הדקל-עצי תמר"},
        {"occupation": "עובד", "employer_label": "יורשי העסק של מנחם בן צבי ז\""},
        {"occupation": "עובד", "employer_label": "בנימיני ירון / חקלאות"},
        {"occupation": "עובד", "employer_label": "גרוס עופרי / חקלאות"},
        {"occupation": "עובד", "employer_label": "הדסים-חברה לפיתוח חקלאי בע\""},
        {"occupation": "עובד", "employer_label": "בנימיני ירון / חקלאות"},
        {"occupation": "עובד", "employer_label": "בנימיני ירון / חקלאות"},
        {"occupation": "עובד", "employer_label": "קבוץ תל קציר / חברים"},
        {"occupation": "עובד", "employer_label": "בנימיני ירון / חקלאות"},
        {"occupation": "עובד", "employer_label": "נגררי השרון בע\"מ - שיווק"},
        {"occupation": "חבר קיבוץ", "employer_label": "קבוץ תל קציר / חברים"},
        {"occupation": "עובד", "employer_label": "בוצר שי / מסגריה"},
        {"occupation": "עצמאי", "employer_label": ""},
        {"occupation": "עובד", "employer_label": "יונג גדי"},
        {"occupation": "עובד", "employer_label": "ירון בנימיני בע\"מ"},
        {"occupation": "עצמאי לא עונה להגדרה", "employer_label": ""},
        {"occupation": "עובד", "employer_label": "עידן עמית שמעון / טל נטפים"},
        {"occupation": "עובד", "employer_label": "טל - נטפים ברמה בע\"מ"},
        {"occupation": "עובד", "employer_label": "בראל רימון תשתיות בע\"מ"},
        {"occupation": "עובד", "employer_label": "מושב מולדת / חברים"},
        {"occupation": "עובד", "employer_label": "מושב שיתופי מולדת / שכירים"},
        {"occupation": "עובד", "employer_label": "מושב מולדת / חברים"},
        {"occupation": "עובד", "employer_label": "אגוזי אייל בע\"מ"},
        {"occupation": "עצמאי", "employer_label": ""},
        {"occupation": "עובד", "employer_label": "אאמבורגריה בע\"מ"},
    ],
    # Model-review gate: mock always returns "no issues" so tests stay deterministic.
    "form_review": {"findings": []},
    "bl_employer_details_labels": [
        ("90100239401", "קבוץ תל קציר / חברים", "תל קציר ד.נ. דאר נע עמק הירדן 1516500"),
        ("90105425400", "שטרית את שמואל-עב' ביוב וניק", "שכונת הגורן יבנאל"),
        ("90103199701", "קבוץ מיצר / חברים", "מיצר ד.נ. ד.נ. רמת הגולן 1293600"),
        ("90105554100", "גמר,הראל וקורן/הדקל-עצי תמר", "משעול הדרור 45/2 מנחמיה 1494500"),
        ("90100822700", "יורשי העסק של מנחם בן צבי ז\"ל", "מושבה כנרת כנרת (מושבה) ד.נ. ד.נ.עמק הירדן 510500"),
        ("90104563300", "בנימיני ירון / חקלאות", "רמות ד.נ. ד.נ.רמת הגולן 1294800"),
        ("90105927900", "גרוס עופרי / חקלאות", "גבעת יואב ד.נ. ד.נ.רמת הגולן 1294600"),
        ("90402262100", "הדסים-חברה לפיתוח חקלאי בע\"מ", "-"),
        ("92340416400", "נגררי השרון בע\"מ - שיווק", "הגאון אליהו 12 רמת גן 5236481"),
        ("90109075300", "בוצר שי / מסגריה", "כנף כנף 1293000"),
        ("90201732600", "יונג גדי", "בית לחם הגלילית 3600700"),
        ("90109661000", "ירון בנימיני בע\"מ", "רמות רמות 1294800"),
        ("90111291200", "עידן עמית שמעון / טל נטפים", "אלעד אלי-עד 1292700"),
        ("90112314100", "טל - נטפים ברמה בע\"מ", "מושב בני יהודה בני יהודה ד.נ. רמת הגולן 1294400"),
        ("90210014800", "בראל רימון תשתיות בע\"מ", "קהלת ציון 8 1, אזור התעשיה עפולה 1830118"),
        ("90203101201", "מושב מולדת / חברים", "מולדת 1913000"),
        ("90203101202", "מושב שיתופי מולדת / שכירים", "מולדת 1913000"),
        ("90221680300", "אגוזי אייל בע\"מ", "מולדת 1913000"),
        ("90237243200", "אאמבורגריה בע\"מ", "שומרים 3 מולדת 1913000"),
    ],
}


class MockVisionExtractor(VisionExtractor):
    """Returns canned responses for the אורי בן פורת example customer.

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
        # All canned responses are dicts; lists get wrapped under 'items'.
        if isinstance(value, list):
            return {"items": value}
        return value
