from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ClientIdentity(BaseModel):
    full_name: str
    id_number: str  # 9-digit ת"ז with check digit


class BankAccount(BaseModel):
    holder_name: str
    id_number: str
    bank_code: str
    bank_name: Optional[str] = None
    branch: str
    account_number: str
    iban: Optional[str] = None
    address: Optional[str] = None  # taken from this doc, used as client address
    issue_date: Optional[date] = None


TagmulimBucket = Literal["hony", "kitzbati_pre_1997", "kitzbati_pre_2000", "kitzbati_chayav"]


class TagmulimFundRow(BaseModel):
    tik_nikuim: str
    kupa_name: str
    member_status: Optional[str] = None  # עצמאי / שכיר / ...
    hony: Decimal = Field(default=Decimal(0))
    kitzbati_pre_2000_or_1997: Decimal = Field(default=Decimal(0))
    kitzbati_chayav: Decimal = Field(default=Decimal(0))
    total: Decimal


class TagmulimReport(BaseModel):
    client: ClientIdentity
    information_date: Optional[date] = None
    request_id: Optional[str] = None
    funds: list[TagmulimFundRow]
    grand_total: Decimal


class PitsuyimEmployerRow(BaseModel):
    tik_nikuim: str
    kupa_name: str
    employer_name: str
    employer_id: Optional[str] = None  # 9-digit
    employment_start_date: Optional[date] = None
    retzef_kitzba_pre_2000: Decimal = Field(default=Decimal(0))
    retzef_kitzba_post_2000: Decimal = Field(default=Decimal(0))
    retzef_pitsuyim_or_maasikim: Decimal = Field(default=Decimal(0))
    shavi_pitsuyim_per_employer: Decimal = Field(default=Decimal(0))


class PitsuyimReport(BaseModel):
    client: ClientIdentity
    information_date: Optional[date] = None
    request_id: Optional[str] = None
    rows: list[PitsuyimEmployerRow]
    grand_total: Decimal


MaslakaProductCategory = Literal[
    "old_pension",        # קרן פנסיה ותיקה
    "new_pension",        # קרן פנסיה חדשה
    "study_fund",         # קרן השתלמות
    "managers_insurance", # ביטוח מנהלים
    "pure_risk_policy",   # פוליסת סיכון טהור
    "gemel",              # קופת גמל
    "policy",             # פוליסה
    "child_savings",      # חסכון לכל ילד
    "other",
]


class MaslakaFund(BaseModel):
    management_company: str  # e.g. "מגדל"
    product_category: MaslakaProductCategory
    product_type_label: Optional[str] = None  # e.g. "פנסיה חדשה מקיפה"
    policy_number: str
    status: Optional[str] = None  # פעיל / לא פעיל
    total_balance: Decimal
    plan_start_date: Optional[date] = None
    first_join_date: Optional[date] = None
    information_date: Optional[date] = None
    tik_nikuim: Optional[str] = None
    ama_number: Optional[str] = None
    management_company_tax_id: Optional[str] = None


class MaslakaReport(BaseModel):
    client: ClientIdentity
    information_date: Optional[date] = None
    request_id: Optional[str] = None
    funds: list[MaslakaFund]


class EmploymentPeriod(BaseModel):
    date_from: date
    date_to: Optional[date] = None
    months: Optional[int] = None
    occupation: str  # עובד / חבר קיבוץ / עצמאי / ...
    employer_label: str  # raw text from report
    note: Optional[str] = None


class BLEmployerDetail(BaseModel):
    tik_maasik: str  # 11-digit BL file number
    employer_name: str
    address: Optional[str] = None


class BLEmploymentHistory(BaseModel):
    client: ClientIdentity
    issue_date: Optional[date] = None
    periods: list[EmploymentPeriod]
    employer_details: list[BLEmployerDetail]


class IDCard(BaseModel):
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    id_number: str  # 9-digit with check digit
    date_of_birth: Optional[date] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    grandfather_name: Optional[str] = None
    place_of_birth: Optional[str] = None
    card_number: Optional[str] = None  # printed card serial (separate from id_number)
    sex: Optional[str] = None
    citizenship: Optional[str] = None


class ClientPicture(BaseModel):
    """Unified view assembled from all parsers, fed into the UI."""

    identity: ClientIdentity
    bank: BankAccount
    id_card: Optional[IDCard] = None
    tagmulim: Optional[TagmulimReport] = None
    pitsuyim: Optional[PitsuyimReport] = None
    maslaka: Optional[MaslakaReport] = None
    bl_history: Optional[BLEmploymentHistory] = None


# ---------------------------------------------------------------------------
# טופס תפעול — Operation form (rep-filled)

PaymentMethod = Literal["credit", "bank_transfer", "bit", "cash"]
ProductType = Literal["pension", "gemel", "policy", "study_fund", "child_savings"]
MoneyType = Literal["tagmulim", "pitsuyim"]
TaxMode = Literal["full", "partial", "exempt"]


class AttachedDocuments(BaseModel):
    """Cover-page checklist of what was attached to the package."""

    id_front: bool = False
    id_back_or_sefach: bool = False
    bank_confirmation: bool = False
    form_161: bool = False
    tax_confirmation: bool = False
    tax_full: bool = False
    employment_end: bool = False
    retzef_employers: bool = False
    funds_release: bool = False
    has_personal_area: bool = False  # יש / אין


class EmployerLine(BaseModel):
    """One row in the per-פעולה employers table."""

    employer_name: str
    # תגמולים column: full amount, specific amount, or not selected.
    tagmulim_full: bool = False
    tagmulim_amount: Optional[Decimal] = None
    # פיצויים column: full-tax or tax-exempt, or not selected.
    pitsuyim_full_tax: bool = False
    pitsuyim_tax_exempt: bool = False


class OperationDetail(BaseModel):
    """One פעולה — one withdrawal from one fund. A form can hold up to 6."""

    insurance_company: str = ""
    product_type: Optional[ProductType] = None
    kupa_number: str = ""
    kupa_vintage: Optional[date] = None
    money_types: list[MoneyType] = Field(default_factory=list)
    tax_mode: Optional[TaxMode] = None
    tax_mode_locked_reason: Optional[str] = None  # e.g. "auto-locked: הוני bucket"
    employers: list[EmployerLine] = Field(default_factory=list)
    notes: str = ""


class OperationFormCover(BaseModel):
    form_date: Optional[date] = None
    rep_name: str = ""
    # Client details (auto-filled from ClientPicture but editable):
    client_first_name: str = ""
    client_last_name: str = ""
    client_id: str = ""
    client_date_of_birth: Optional[date] = None
    client_phone: str = ""
    client_city: str = ""
    # Deal:
    amount_total: Optional[Decimal] = None
    amount_collected: Optional[Decimal] = None
    payment_method: Optional[PaymentMethod] = None
    # Attached docs checklist:
    attached: AttachedDocuments = Field(default_factory=AttachedDocuments)
    # Trigger questions:
    pull_retzef_from_bituach_leumi: bool = False
    pull_for_debt_closure: bool = False
    notes: str = ""


class OperationForm(BaseModel):
    cover: OperationFormCover
    operations: list[OperationDetail] = Field(default_factory=list)
    # The form template has fixed slots for up to 6 פעולה pages — empty slots
    # render as blank sub-pages just like the reference PDF.
    max_operations: int = 6
