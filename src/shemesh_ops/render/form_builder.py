"""Build a sample OperationForm using synthetic placeholder data.

Demonstrates the render pipeline + serves as a fixture for the render test.
All values are made-up; for a real client, build OperationForm directly
from the actual extracted ClientPicture.
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
    """Build a synthetic OperationForm from a ClientPicture.

    Uses placeholder amounts/dates/notes; the rep is expected to overwrite
    these in the UI. Pre-fills client details and the bank's city/address.
    """

    cover = OperationFormCover(
        form_date=date.today(),
        rep_name="",
        client_first_name=(picture.id_card.first_name if picture.id_card else "") or "",
        client_last_name=(picture.id_card.last_name if picture.id_card else "") or "",
        client_id=picture.identity.id_number,
        client_date_of_birth=(picture.id_card.date_of_birth if picture.id_card else None),
        client_phone="",
        client_city=(picture.bank.address or "").split(",")[-1].strip() if picture.bank.address else "",
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

    # Build up to two operation rows from the extracted maslaka funds.
    operations: list[OperationDetail] = []
    if picture.maslaka:
        for fund in picture.maslaka.funds[:2]:
            operations.append(OperationDetail(
                insurance_company=fund.management_company or "",
                product_type="pension" if "pension" in (fund.product_category or "") else None,
                kupa_number=fund.policy_number,
                kupa_vintage=fund.plan_start_date,
                money_types=["tagmulim"],
                tax_mode="full",
                employers=[],
                notes="",
            ))

    return OperationForm(cover=cover, operations=operations)
