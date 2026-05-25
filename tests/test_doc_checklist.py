from datetime import date

from shemesh_ops.doc_checklist import (
    EmployerReleaseStatus,
    required_documents,
)
from shemesh_ops.models import (
    BankAccount,
    ClientIdentity,
    ClientPicture,
    IDCard,
    OperationDetail,
)


def _bank() -> BankAccount:
    return BankAccount(
        holder_name="", id_number="000000000", bank_code="", branch="", account_number=""
    )


def _picture(dob: date) -> ClientPicture:
    return ClientPicture(
        identity=ClientIdentity(full_name="", id_number="000000000"),
        bank=_bank(),
        id_card=IDCard(full_name="", id_number="000000000", date_of_birth=dob),
    )


TODAY = date(2026, 5, 24)


def test_base_docs_always_required():
    p = _picture(dob=date(1990, 1, 1))
    op = OperationDetail(money_types=["tagmulim"], insurance_company="חברה דוגמה ב")
    res = required_documents(op, p, as_of=TODAY)
    keys = res.required_keys()
    assert {"id_front", "id_back_or_sefach", "bank_confirmation"}.issubset(keys)


def test_tagmulim_under_60_requires_employment_end_or_retzef():
    p = _picture(dob=date(1990, 1, 1))  # age 36
    op = OperationDetail(money_types=["tagmulim"], insurance_company="חברה דוגמה ב")
    res = required_documents(op, p, as_of=TODAY)
    keys = res.required_keys()
    assert "employment_end" in keys
    assert "retzef_employers" in keys
    assert "form_161" not in keys  # tagmulim only — no 161


def test_over_60_skips_employment_docs():
    p = _picture(dob=date(1955, 1, 1))  # age ~71
    op = OperationDetail(money_types=["tagmulim"], insurance_company="חברה דוגמה ב")
    res = required_documents(op, p, as_of=TODAY)
    keys = res.required_keys()
    assert "employment_end" not in keys
    assert "retzef_employers" not in keys
    assert any("60" in n for n in res.notes)


def test_pitsuyim_requires_161():
    p = _picture(dob=date(1990, 1, 1))
    op = OperationDetail(money_types=["pitsuyim"], insurance_company="חברה דוגמה ב")
    res = required_documents(op, p, as_of=TODAY)
    assert "form_161" in res.required_keys()


def test_altshuler_retzef_message_mentions_2_years():
    p = _picture(dob=date(1990, 1, 1))
    op = OperationDetail(money_types=["tagmulim"], insurance_company="אלטשולר שחם")
    res = required_documents(op, p, as_of=TODAY)
    retzef_doc = next(d for d in res.docs if d.key == "retzef_employers")
    assert "2" in retzef_doc.reason


def test_harel_retzef_message_mentions_2_years():
    p = _picture(dob=date(1990, 1, 1))
    op = OperationDetail(money_types=["tagmulim"], insurance_company="הראל")
    res = required_documents(op, p, as_of=TODAY)
    retzef_doc = next(d for d in res.docs if d.key == "retzef_employers")
    assert "2" in retzef_doc.reason


def test_pitsuyim_within_4_months_requires_funds_release():
    p = _picture(dob=date(1990, 1, 1))
    op = OperationDetail(money_types=["pitsuyim"], insurance_company="חברה דוגמה ב")
    emp = [EmployerReleaseStatus(
        employer_name="דוגמה-ב",
        has_161=True,
        has_funds_release=False,
        employment_end_date=date(2026, 3, 1),  # 2.7 months ago
    )]
    res = required_documents(op, p, employer_release=emp, as_of=TODAY)
    assert "funds_release" in res.required_keys()


def test_pitsuyim_over_4_months_no_funds_release_needed():
    p = _picture(dob=date(1990, 1, 1))
    op = OperationDetail(money_types=["pitsuyim"], insurance_company="חברה דוגמה ב")
    emp = [EmployerReleaseStatus(
        employer_name="דוגמה-ב",
        has_161=True,
        has_funds_release=False,
        employment_end_date=date(2025, 1, 1),  # 16 months ago
    )]
    res = required_documents(op, p, employer_release=emp, as_of=TODAY)
    assert "funds_release" not in res.required_keys()


def test_bl_employment_history_required_when_employer_lacks_161():
    p = _picture(dob=date(1990, 1, 1))  # under 60
    op = OperationDetail(money_types=["pitsuyim"], insurance_company="חברה דוגמה ב")
    emp = [
        EmployerReleaseStatus(employer_name="OK_employer", has_161=True),
        EmployerReleaseStatus(employer_name="MISSING_employer", has_161=False, has_funds_release=False),
    ]
    res = required_documents(op, p, employer_release=emp, as_of=TODAY)
    bl = [d for d in res.docs if d.key == "bl_employment_history"]
    assert len(bl) == 1
    assert "MISSING_employer" in bl[0].reason


def test_bl_employment_history_not_required_if_over_60():
    p = _picture(dob=date(1955, 1, 1))  # over 60
    op = OperationDetail(money_types=["pitsuyim"], insurance_company="חברה דוגמה ב")
    emp = [EmployerReleaseStatus(employer_name="MISSING_employer", has_161=False)]
    res = required_documents(op, p, employer_release=emp, as_of=TODAY)
    assert "bl_employment_history" not in res.required_keys()
