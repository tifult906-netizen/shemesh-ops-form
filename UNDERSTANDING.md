# טופס תפעול – Shemesh Sales Rep Operation Form (v2)

*Rewritten after reading the example folder: ID photos, bank confirmation, 2× מסלקה reports (תגמולים + פיצויים), the example filled `טופס תפעול`, and the `מסמכים נדרשים לכל פעולה` rules sheet.*

---

## 1. Big-picture flow

```
   ┌─────────────────────────┐
   │ Rep picks operation     │   ← driver of everything
   │ (1 of 8 types)          │
   └────────────┬────────────┘
                │
   ┌────────────▼────────────┐
   │ Rep uploads required    │
   │ docs (driven by op type)│
   └────────────┬────────────┘
                │
   ┌────────────▼────────────┐
   │ Local model extracts:   │
   │  • ID: vision LLM       │
   │  • PDFs: text parse +   │
   │    LLM structuring      │
   └────────────┬────────────┘
                │
   ┌────────────▼────────────┐
   │ Rep reviews + picks:    │
   │  source fund (קופה)     │
   │  source employer(s)     │
   │  type (תגמ׳ / פיצ׳)     │
   │  tax (מלא/חלקי/פטור)    │
   │  destination / מפעיל    │
   └────────────┬────────────┘
                │
   ┌────────────▼────────────┐
   │ Render one unified      │
   │ Hebrew RTL טופס תפעול   │
   │ + checklist of docs     │
   └─────────────────────────┘
```

---

## 2. Scope: money withdrawal (תגמולים and/or פיצויים)

**v3 scope (after Avihay's corrections):** the tool handles **withdrawal** operations. Out of scope: הלוואה, אובדן כושר, שארים, נפטר. **In scope:**

| Product container (סוג מוצר) | Money types in scope          |
|------------------------------|-------------------------------|
| קרן פנסיה                    | תגמולים, פיצויים              |
| קופת גמל                     | תגמולים, פיצויים              |
| פוליסה                       | תגמולים, פיצויים              |
| **קרן השתלמות**              | תגמולים (with 6-year rule, §2a) |
| **חסכון לכל ילד**            | (withdrawal)                  |

**Both money types can be selected in the same פעולה** — it's a checkbox group, not radio. The form template's מעסיקים table already has parallel תגמולים/פיצויים columns precisely so a single פעולה can pull both from the same source.

### Per money-type rules

| Money type    | Driver of UI/doc/rule differences                                   |
|---------------|---------------------------------------------------------------------|
| **תגמולים**  | per-fund withdrawal; tagmulim report drives fund list               |
| **פיצויים**  | per-employer withdrawal; pitsuyim report drives employer list; **additionally requires** סיום העסקה / רצף מעסיקים, 161 / אישור מס פיצויים, and שחרור כספים if <4 months since employment end |

Shared base docs: ID (biometric → both sides; old → front + ספח) + bank confirmation / cancelled check. רצף requires 1 year since employment end (2 years for **אלטשולר** and **הראל**); waived entirely if client is **over 60**.

### 2a. קרן השתלמות special tax rule

Default tax behaviour for the source fund being withdrawn:

| Account age of source קה"ש | Result                                                                              |
|----------------------------|-------------------------------------------------------------------------------------|
| ≥ 6 years                  | **Tax-free** (פטור ממס) even on הוני                                                |
| < 6 years (תגמולים הוני)   | **35% tax** by default                                                              |

**Cross-fund vintage override:** if the client has *any other* קרן השתלמות account that is ≥ 6 years old (even at a different company), the rep can use that older account's vintage to make a withdrawal from the newer (<6 yrs) fund tax-free.

→ UI implication: when the user picks a קרן השתלמות source fund <6 yrs old, scan the rest of their קה"ש funds. If any is ≥6 yrs, show a "השתמש בוותק מ-[fund name, X years]" toggle to switch the tax mode to פטור. Without it, default to 35%.

### 2b. No "destination" anywhere

This is pure withdrawal → money lands in the client's bank account. The destination is **deduced from the bank confirmation** (`אישור ניהול חשבון`), not entered by the rep. No "destination operator", "מפעיל יעד", or "destination tab" anywhere in the UI or the form.

---

## 3. Required documents per operation (extracted from rules sheet)

### Base for ALL operations
- **ת"ז (ID)**:
  - אם ביומטרי → צילום משני צדדים
  - אם הישן → צילום ת"ז קדמי + ספח פתוח ומלא
- **אישור ניהול חשבון** / צ'ק מבוטל
- **טופס תפעול** (the output we're generating)

### Op-specific additions
- **תגמולים / פיצויים withdrawal**:
  - סיום העסקה / רצף מעסיקים
    - רצף requires ≥1 year since employment end (≥2 years for **אלטשולר** and **הראל**)
    - **Over age 60 → not required at all**
  - For פיצויים only:
    - שחרור כספים (if <4 months since employment end)
    - 161 תקין / אישור מס פיצויים
  - **אישור תקופות ביטוח ומעסיקים** (from ביטוח לאומי) — required when:
    - Client is **under 60**, AND
    - Rep wants to withdraw from a specific employer that does **NOT** have a 161 / שחרור העסקה available for this client.
    - Acts as proof-of-employment-history fallback. Source: National Insurance Institute, lists every employment period the client ever had (dates, occupation type, employer name) + employer-file table with `תיק המעסיק` numbers and addresses.
- **חסכון לכל ילד**:
  - Mother's ID also (only if child <21)
  - Bank confirmation must be in the *child's* name
- **הלוואה**:
  - Spouse ID + ספח if married
  - 3 months bank statements (עו"ש)
  - 3 last payslips
  - בנק debit authorization w/ insurer-specific מוסד code
  - תפעול must specify: loan amount, repayment period, interest type (variable/fixed)
- **אובדן כושר עבודה**:
  - 12 payslips before disability date (or annual tax report if self-employed)
  - 90+ days of sick days
  - Occupational doctor report (if >1 year disability)
  - All medical docs explaining inability to work
  - All hospitalization summaries
  - Employer scope confirmation (% role + dates before and after injury)
- **שארים**:
  - Survivor's ID + deceased's ID
  - Death certificate
  - Will / inheritance order + execution order
  - Letter on cause of death / hospital discharge
- **משיכת כספי נפטר**:
  - Heir's ID (each one if multiple) + deceased's ID
  - Death certificate
  - Will / inheritance order + execution order
  - הר הכסף report

### Cross-cutting rules
- Every treatment must have a **signed ב1** form (existing Shemesh process — SMS link, sign, etc.)
- For שארים / נפטר: register both the heir AND the deceased in the SMS system, ב1 each

---

## 4. What each document gives us (extraction targets)

### 4a. Israeli Biometric ID (`תעודת זהות ביומטרית`) – **2 photos, vision-LLM only**
From this example (אורי בן פורת):

| Side  | Fields                                                                                       |
|-------|---------------------------------------------------------------------------------------------|
| Front | שם פרטי (אורי), שם משפחה (בן פורת), ת"ז (029742590), תאריך לידה (15.02.1973), תאריך הנפקה (7.9.2022), תוקף (04.09.2032) |
| Back  | שם האב (יוסף), שם האם (מיכל), שם הסב (ראובן), מקום לידה (ישראל), מעמד (אזרחות ישראלית), מין (זכר), מספר הכרטיס (011310248) |

> ⚠️ **Address is NOT on the biometric ID** — newer Israeli ID cards omit it. Address comes from the **bank confirmation** instead (or from the old-style ספח if the customer has one).

### 4b. אישור ניהול חשבון (Bank confirmation) – **PDF with selectable text**
- שם חשבון (בן פורת אורי)
- בנק (12 = הפועלים), סניף (549), חשבון (383654)
- IBAN (IL090125490000000383654)
- **כתובת החשבון** (הפרדס 8, מולדת) ← address source
- Issue date of confirmation (17/03/2026)

### 4c. דוח יתרות תגמולים (Tagmulim balances) – **PDF with selectable text**
Per-fund breakdown:
- שם קופה (e.g. קרן הפנסיה עתודות)
- מספר תיק ניכויים (e.g. 935947184)
- מעמד עמית (עצמאי / שכיר / מנהלת ...)
- Per-bucket balances: הוני / קיצבתי לפני 2000 / לפני 1997 / קצבתי חייב
- סה"כ צבירה
- **Grand total** (₪135,143 in example)

> The tagmulim report does NOT list employers per fund — only fund-level totals.

### 4d. דוח יתרות פיצויים (Pitsuyim balances) – **PDF with selectable text**
Per-fund × per-employer breakdown:
- שם קופה (e.g. מגדל מקפת אישית)
- מספר תיק ניכויים
- שם מעסיק (e.g. רימון פיתוח וכבישים בעמ)
- מספר מזהה מעסיק (e.g. 512255944)
- תאריך תחילת העסקה
- 4 amount columns: ברצף קצבה עד 31.12.1999 / ברצף קצבה מ-1.1.2000 / ברצף פיצויים או רצף מעסיקים / שווי פיצויים למעסיק
- Grand total (₪30,085 in example)

> Pitsuyim report IS the source of truth for the **employer list** — and the form's "מעסיקים" table per פעולה is populated from here.

### 4e.5. דוח מסלקה (full clearing-house report) – **PDF with selectable text** (with caveat)
11-page comprehensive report. Same `מספר הבקשה` as the 2 separate reports → comes from the **same single clearing-house query** (no extra burden on client to request).

**What this report uniquely provides** (vs the 2 separate reports):
- Per-fund **plan-start date** (`תאריך תחילת תכנית`) — required for the קה"ש 6-year tax rule (§2a)
- Per-fund **status** (פעיל / לא פעיל) — lets us hide inactive funds in the UI
- **קרן השתלמות funds** themselves — the תגמולים report only enumerates pension funds; השתלמות only shows up here
- Also visible: ביטוח מנהלים, פוליסות סיכון טהור, fees, yields, projected pensions, insurance coverage detail (for future scope)

**What this report does NOT have** (so the 2 separate reports stay required):
- Tax-bucket breakdown (הוני / קצבתי לפני 2000 / קצבתי חייב) — only in תגמולים report
- Per-employer פיצויים breakdown — only in פיצויים report

**Decision: require all 3 reports** (מסלקה + תגמולים + פיצויים). Cost to client = 0 (one query).

**Extraction caveat — reversed Hebrew on pages 1-8:** the issuing tool emits Hebrew text with letters reversed within each word (e.g. "מגדל" stored as "לדגמ"). Numbers, dates, IDs extract cleanly. Hebrew labels need a per-token un-reverser pass. Pages 9+ are normal. Plan: parse with pdfplumber + a `reverse_hebrew_tokens(text)` helper that flips runs of Hebrew chars within each token. Fallback if that gets too brittle: render page-to-PNG via pymupdf and vision-LLM the labels.

### 4f. אישור תקופות ביטוח ומעסיקים (National Insurance employment history) – **PDF with selectable text**, conditional
Multi-page PDF from ביטוח לאומי. Two tables to extract:

**Periods table** (per row):
- תאריך מ, תאריך עד
- חודשים (duration in months)
- עיסוק (עובד / חבר קיבוץ / עצמאי / etc.)
- פרטי המדווח (employer / קיבוץ / "עצמאי" label)
- הערה (free-text remark, e.g. "עצמאי לא עונה להגדרה")

**Employer-details table** (cross-reference, at end):
- תיק המעסיק (employer's tax file number, e.g. 90210014800)
- שם המעסיק
- כתובת

→ **Use:** when a פיצויים withdrawal targets an employer that lacks 161 / שחרור העסקה, this doc is required as the proof-of-employment fallback. The pitsuyim report shows the *money*; this doc shows the *employment relationship existed*.

→ **Cross-reference logic the tool can run automatically:** match `מספר מזהה מעסיק` from the pitsuyim report against `תיק המעסיק` here. Caveat: the IDs may differ in format/length (the pitsuyim doc shows 9-digit מזהה, BL shows 11-digit תיק). For the example customer, pitsuyim has `512255944` (רימון פיתוח וכבישים) and BL has `90210014800` (בראל רימון תשתיות בעמ) — same company, different IDs. So fuzzy-match on **company name** first, with `תיק המעסיק` as a tiebreaker.

> ⚠️ The PDF's text appears right-to-left reversed when extracted naively (visible in the bash extraction we did). Will need RTL post-processing — pdfplumber + a Hebrew-aware reorder pass. Worth noting that the financial PDFs (bank, תגמ׳, פיצ׳) extract cleanly; only this one's layout is more painful.

---

## 5. The output form (one unified template)

From the example `טופס תפעול פידיון תגמולים.pdf` — 1 cover page + N (up to 6) "פרטי פעולה" pages:

### Cover page
| Section            | Fields                                                                                             |
|--------------------|----------------------------------------------------------------------------------------------------|
| Header             | תאריך, שם נציג                                                                                     |
| פרטי הלקוח         | שם פרטי, שם משפחה, ת"ז, תאריך לידה, טלפון נייד, עיר מגורים                                          |
| פרטי העסקה         | סכום כולל, סכום שנגבה, איך שולם (אשראי / העברה בנקאית / ביט / מזומן)                                |
| מסמכים מצורפים     | Checklist: ת"ז קדמי / אחורי-ספח / אישור ניהול חשבון \| מס: 161 / אישור מס / מס מלא \| סיום-רצף: סיום העסקה / רצף מעסיקים / שחרור כספים \| איזור אישי: יש / אין |
| Yes/No toggles     | האם להוציא רצף מעסיקים מביטוח לאומי? \| האם להוציא לצורך סגירת חוב?                                  |
| הערות              | free text                                                                                          |

### Per פעולה (1 to 6 separate operations within one form)
| Section            | Fields                                                                                             |
|--------------------|----------------------------------------------------------------------------------------------------|
| חברת ביטוח         | text (e.g. מגדל, עתודות פנסיה ותיקה)                                                                |
| סוג מוצר           | one of: קרן פנסיה / קופת גמל / פוליסה / קרן השתלמות / חסכון לילד                                    |
| מספר קופה          | from מסלקה report                                                                                  |
| וותק הקופה         | start date                                                                                         |
| סוג הכספים         | תגמולים / פיצויים                                                                                  |
| מיסוי              | מס מלא / מס חלקי / פטור ממס                                                                        |
| מעסיקים            | rows of (שם מעסיק, תגמולים? [מלוא הסכום / על סך X], פיצויים? [מלוא הסכום / על סך X], מס מלא?, פטור מס?) |
| הערות              | per-פעולה free text (e.g. "מבקש למשוך תגמולים במס מלא מ-...")                                       |

**The example used 2 פעולה pages**: one for מגדל קרן פנסיה (employers: מולדת + רימון), one for עתודות פנסיה ותיקה (employer: טל-נטפים). All withdrawals were תגמולים / מס מלא.

---

## 6. Extraction strategy (revised)

The ID is the only thing that needs OCR. All 3 PDFs are text-PDFs with selectable text — much easier and more reliable than OCR.

| Document          | Approach                                                                                  |
|-------------------|-------------------------------------------------------------------------------------------|
| ID (2 JPEGs)      | **Vision LLM** locally — Qwen2.5-VL-7B or Qwen2-VL-7B (good Hebrew). Fall back to InternVL2 if needed. |
| Bank PDF          | `pdfplumber` + regex/LLM for structured fields                                            |
| Tagmulim PDF      | `pdfplumber` table extraction → JSON list                                                 |
| Pitsuyim PDF      | `pdfplumber` table extraction → JSON list (this populates the employer dropdown)          |

Privacy: all three steps run locally (vision LLM via `transformers` or `vllm`, PDF parsing in-process).

---

## 7. UI sketch (Hebrew RTL web app)

```
┌────────────────────────────────────────────┐
│  שמש – טופס תפעול                          │
├────────────────────────────────────────────┤
│ 1. בחר פעולה  ▾  [משיכת תגמולים]            │  ← drives required-docs list
├────────────────────────────────────────────┤
│ 2. העלאת מסמכים                            │
│    ☐ ת"ז (קדמי + אחורי / קדמי + ספח)       │
│    ☐ אישור ניהול חשבון / צ'ק מבוטל          │
│    ☐ דוח יתרות תגמולים (מסלקה)             │
│    ☐ דוח יתרות פיצויים (מסלקה)             │
│    [+ dynamic op-specific docs]            │
├────────────────────────────────────────────┤
│ 3. סקירת מידע שחולץ (לקוח + בנק = יעד הכסף)│  ← bank from confirmation = destination, no extra field
│    שם:     אורי בן פורת        [✎ ערוך]    │
│    ת"ז:    029742590           [✎]         │
│    כתובת: הפרדס 8, מולדת        [✎]        │
│    בנק (יעד התשלום):                       │
│         הפועלים 12 / סניף 549 / 383654 [✎] │
├────────────────────────────────────────────┤
│ 4. פעולה #1                       [+ הוסף] │
│    חברת ביטוח (מקור): [מגדל ▾]             │
│    סוג מוצר:   [קרן פנסיה ▾]              │
│    קופה:       [935967851 ▾]              │
│    סוג כסף:    ☑ תגמולים  ☑ פיצויים        │  ← checkboxes — both allowed
│    מיסוי:      [מס מלא ▾]                 │  ← auto-locks to "פטור" if הוני bucket
│    מעסיקים מהדוח:                          │  ← split into 2 sub-tables when both money types are checked
│      ☑ רימון פיתוח – פיצ׳ ₪13,805         │
│      ☐ מולדת כפר בני ברית – פיצ׳ ₪0        │
│      ☐ טל-נטפים ברמה – פיצ׳ ₪6,748        │
│    [קה"ש בלבד: זוהה ותק <6 שנים. השתמש    │
│     בוותק מ-[שם קופה אחרת] (8 שנים)? ▢ ]  │
│    הערות: [_______________________]        │
├────────────────────────────────────────────┤
│ 4.5. בדיקת מודל                           │  ← LLM sanity-check before generating PDF
│   "האם הערכים תואמים את מסמכי המקור?"      │
│   • flags garbled Hebrew                  │
│   • flags numeric mismatches              │
│   • rep can override or fix               │
├────────────────────────────────────────────┤
│ 5. תצוגה מקדימה + ייצוא ל-PDF              │
└────────────────────────────────────────────┘
```

Notes:
- Step 2's checklist is **conditional** on Step 1's operation type + the **client's age (<60)** + whether the selected employer has 161 / שחרור (triggers the BL "אישור תקופות ביטוח ומעסיקים" requirement).
- Step 3 is the LLM-extraction review — every field editable so the rep is the final authority. The bank account is implicitly the **destination of the payment** — no separate destination field anywhere.
- Step 4 can repeat for multiple operations within one form (up to 6 per template).
- Step 4 — when **both** money types are checked, the מעסיקים sub-table renders two columns (תגמ׳ / פיצ׳), as in the actual paper form.
- Step 5 renders the same PDF layout you uploaded (we'll generate via WeasyPrint or ReportLab w/ Hebrew RTL support).

---

## 8. Settled answers (after round 2)

### Insurance companies — **18 companies**, full list in `insurance_companies.csv`
מנורה, אלטשולר שחם, מיטב דש, הפניקס, מור, רום, הראל, עמיתים (/ מבטחים), כלל, מגדל, גל/כלנית, מינהל, אינפיניטי, קו הבריאות, עתודות, למורים וגננות, אנליסט, ילין לפידות.

Bonus: the CSV maps **(company × סוג קופה) → email address** — so once we know the company and the product type, we know exactly which inbox the form should be sent to. This is a free automation hook for "Step 5: deliver" later.

### Reps (7) — for the שם נציג dropdown
אוהד, נדב, יוני, שי, דורון, מאי, אגם

### Operation scope — **withdrawal only**, money type is תגמולים OR פיצויים (see §2)

### "מפעיל" = source of money in the קופה
i.e. the **depositor** — for פיצויים that's the employer (from the pitsuyim report's per-מעסיק rows); for תגמולים it's the employer for שכיר accounts or the client themselves for עצמאי. The form's "מעסיקים" table is this list.

### Tax-mode rule
Rep picks (מס מלא / מס חלקי / פטור ממס), **except**: if the money is **הוני**-classified, auto-default to **פטור ממס** (capital money is tax-free by default). Source: the tagmulim report's per-bucket columns include "הוני" — if the selected bucket is הוני, lock the tax field to פטור and explain why.

---

## 9. Still open

### Nice-to-have (not blocking)
1. **Branding** — Shemesh logo, brand colors, font preference for the generated PDF.
2. **Delivery** — generated PDF: just download? Save to disk? Email to the company inbox (we have those now)? Push to Telegram? My default: download + save locally, with an opt-in "email to insurer" button once we're comfortable.
3. **Auth** — login per rep, or shared internal-LAN tool? My default: simple rep-picker dropdown (no password) until you say otherwise.
4. **A second example, for פיצויים** — would still validate I caught the תגמולים/פיצויים conditional differences. The form structure looks identical, but the doc checklist diverges (161, שחרור כספים, etc.) — one real example will confirm.

### Decisions I'll proceed with unless you push back
- **Vision model**: Qwen2.5-VL-7B locally for ID extraction
- **PDF parsing**: pdfplumber for the 3 text-PDFs
- **Web framework**: FastAPI + Hebrew RTL frontend
- **PDF render**: WeasyPrint w/ NotoSansHebrew, matching your reference layout
- **Storage**: SQLite (rep submissions, extracted JSON, blob path to generated PDF)
- **Project location**: standalone at `~/projects/shemesh-ops-form/`

---

## 10. Suggested build order

1. **PDF parsers** — `bank`, `tagmulim`, `pitsuyim` (clean text-PDFs). Deterministic, tested against this very example. **Demo target**: paste 3 PDFs → console-print clean JSON of customer, accounts, per-employer pitsuyim breakdown.
2. **BL employment-history parser** (`אישור תקופות ביטוח ומעסיקים`) — same demo target, harder because of RTL extraction. Pair with company-name fuzzy-match against the pitsuyim employer list.
3. **Skeleton FastAPI app** + Hebrew RTL static front-end shell.
4. **Vision-LLM ID extraction** (local), with manual-override UI so the rep is final authority.
5. **Form-rendering pipeline** (WeasyPrint → PDF matching your reference layout).
6. **Tax-mode auto-lock** for הוני buckets + the קה"ש 6-year rule (incl. cross-fund vintage override).
7. **Per-operation employer multi-select** (פיצויים rows from pitsuyim report; תגמולים rows from tagmulim's per-קופה list; both-checked mode renders dual table).
8. **Conditional doc checklist** with all gates: money type, age-60, Altshuler/Harel 2-yr, BL doc when an employer lacks 161/שחרור.
9. **Model-review gate** (step 4.5 in §7) — LLM compares final values against source docs, flags garbled Hebrew or numeric mismatches, blocks PDF render until rep acknowledges.
10. **Submission + storage** (SQLite + saved PDF).
11. *(Stretch)* **Auto-route email** to the right insurer inbox from `insurance_companies.csv` when the rep clicks send.

Step 1+2 alone get us from raw PDFs → structured JSON of every account + employer + employment-history-cross-reference for this customer. That's the first demo back to you.
