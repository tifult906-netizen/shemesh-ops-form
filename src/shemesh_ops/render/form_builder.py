"""Build a sample OperationForm matching the reference filled PDF.

The reference is `טופס תפעול פידיון תגמולים.pdf` for אורי בן פורת:
  - Date 15/03/2026
  - Deal: ₪2,000 total, 0 collected, paid via העברה בנקאית
  - Attached: ת.ז קדמי + אחורי-ספח + אישור ניהול חשבון + מס מלא + רצף מעסיקים, אזור אישי = יש
  - Both yes/no toggles = לא
  - Operation 1: מגדל קרן פנסיה, kupa 29742590, vintage 01/12/2024, תגמולים, מס מלא
    Employers: מולדת + רימון (both with תגמולים full)
  - Operation 2: עתודות פנסיה ותיקה, kupa 902974259052, vintage 01/04/1995, תגמולים, מס מלא
    Employer: טל-נטפים ברמה
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..models import (
    AttachedDocuments,
    ClientPicture,
    EmployerLine,
    OperationDetail,
    OperationForm,
    OperationFormCover,
)


def build_example_form(picture: ClientPicture) -> OperationForm:
    """Reproduce the reference form for אורי בן פורת given his extracted picture."""

    cover = OperationFormCover(
        form_date=date(2026, 3, 15),
        rep_name="",
        client_first_name=picture.id_card.first_name if picture.id_card else "אורי",
        client_last_name=picture.id_card.last_name if picture.id_card else "בן פורת",
        client_id=picture.identity.id_number,
        client_date_of_birth=picture.id_card.date_of_birth if picture.id_card else date(1973, 2, 15),
        client_phone="0523434466",
        client_city=(picture.bank.address or "").split(",")[-1].strip() if picture.bank.address else "מולדת",
        amount_total=Decimal("2000"),
        amount_collected=Decimal("0"),
        payment_method="bank_transfer",
        attached=AttachedDocuments(
            id_front=True,
            id_back_or_sefach=True,
            bank_confirmation=True,
            tax_full=True,
            retzef_employers=True,
            has_personal_area=True,
        ),
        pull_retzef_from_bituach_leumi=False,
        pull_for_debt_closure=False,
        notes="",
    )

    op1 = OperationDetail(
        insurance_company="מגדל",
        product_type="pension",
        kupa_number="29742590",
        kupa_vintage=date(2024, 12, 1),
        money_types=["tagmulim"],
        tax_mode="full",
        employers=[
            EmployerLine(employer_name="מולדת כפר בני ברית", tagmulim_full=True),
            EmployerLine(employer_name="רימון פיתוח וכבישים בעמ", tagmulim_full=True),
        ],
        notes="מבקש למשוך תגמולים במס מלא מרימון פיתוח וכבישים בעמ ומולדת כפר בני ברית",
    )

    op2 = OperationDetail(
        insurance_company="עתודות פנסיה ותיקה",
        product_type="pension",
        kupa_number="902974259052",
        kupa_vintage=date(1995, 4, 1),
        money_types=["tagmulim"],
        tax_mode="full",
        employers=[
            EmployerLine(employer_name='טל-נטפים ברמה בע"מ', tagmulim_full=True),
        ],
        notes='מבקש למשוך תגמולים במס מלא מטל-נטפים ברמה בע"מ',
    )

    return OperationForm(cover=cover, operations=[op1, op2])
