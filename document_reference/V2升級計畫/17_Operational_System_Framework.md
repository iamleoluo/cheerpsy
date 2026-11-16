# 17 · Operational System Framework (as built)

**CheerPsy — Tzu-En Psychotherapy Clinic · Practice Management System, Version 2**

> **What this document is.** A complete structural reference for the system **as it exists today**, written in English. It describes what has actually been built and verified, not what is planned. Where a design decision was made deliberately, the decision and its rationale are stated; where a gap remains open, it is listed as a gap rather than glossed over.
>
> **What this document is not.** It is not the forward plan. The next-generation architecture — the five-layer model that separates business pipelines from base facts and introduces a mediating module layer — is document 16. This document is the baseline that document 16 proposes to restructure.
>
> **Format.** Markdown rather than the HTML used by documents 00–15, because this file is intended to be read on a branch and in review tools, where Markdown renders and HTML does not.
>
> **Verification basis.** Every structural claim below was checked against the source tree on 2026-11-17. Counts (tests, invariants, coverage checks, routers, pages, plans, rooms) were measured, not recalled.

---

## Contents

1. [Operating context](#1--operating-context)
2. [Actors and authority](#2--actors-and-authority)
3. [The operational spine](#3--the-operational-spine)
4. [Domain model overview](#4--domain-model-overview)
5. [The consultation pipeline](#5--the-consultation-pipeline)
6. [Institutional funding subsystem](#6--institutional-funding-subsystem)
7. [Money](#7--money)
8. [Space and scheduling resources](#8--space-and-scheduling-resources)
9. [Identifiers and numbering](#9--identifiers-and-numbering)
10. [Reporting](#10--reporting)
11. [The correctness regime](#11--the-correctness-regime)
12. [Application surface](#12--application-surface)
13. [Platform and deployment](#13--platform-and-deployment)
14. [Known gaps and accepted debt](#14--known-gaps-and-accepted-debt)
15. [Appendix: enumerations](#15--appendix-enumerations)

---

## 1 · Operating context

The clinic delivers psychotherapy through four payment arrangements that coexist in every working day:

| Arrangement | Who pays | Consequence for the system |
|---|---|---|
| **Self-pay, per session** | The client, at the counter, on the day | Cash or transfer collected at reception; receipt issued immediately |
| **Self-pay, monthly or multi-session** | The client, in arrears | No collection at the counter; an accumulating balance settled later |
| **Institutionally funded** | A government body or organisation, against a contract | Entitlement must be tracked per person, priced by contract rules, and later claimed |
| **Venue use without therapy** | A supervisor, an outside group, an institution | Space is consumed and a fee may be due, but no clinical session exists |

Three properties of the clinic shape the whole design:

1. **Physical capacity is fixed.** Twelve consulting rooms (`1A`, `2A`–`2E`, `3A`–`3F`) plus a fifth-floor hall. Nothing the software does can create more.
2. **Institutional funding is irregular.** The clinic's contract register lists **54 funded plans across 32 funding bodies**, with seven distinct pricing models, eight distinct entitlement rules and five distinct claim schedules. No two are quite alike, and they change at each contract renewal.
3. **One counter handles everything.** All money enters through reception, so reconciliation is a single daily activity regardless of what generated the charge.

The system's purpose is to make the daily operation of this clinic executable by reception staff without specialist knowledge, while keeping the financial record defensible.

---

## 2 · Actors and authority

Four roles, each with a code prefix used in identifiers:

| Role | Prefix | Authority |
|---|---|---|
| **Administrator** | `A` | Full access: user accounts, institutions, contracts, plans, rate rules, data import and export, audit trail |
| **Accountant** | `C` | Financial reporting, reconciliation and claims; cannot create cases or appointments |
| **Reception / front desk** | `S` | Cases, appointments, check-in, collection, receipts, claim preparation; no administrative configuration |
| **Therapist** | `T` | Own schedule, own caseload, own compensation; confirms documentation for institutional claims |

Two mechanisms support this:

- **Account provisioning is invitation-based.** An administrator issues an invitation key carrying the intended role and user code; the recipient sets their own password. The same mechanism serves password resets. Credentials are never set on another person's behalf.
- **Every mutation is audited.** The audit log records table, record, action, acting user, and the complete before and after state as structured data. Date and timestamp values are normalised before storage so that the record remains machine-readable.

The interface is a **dual-role shell**: reception and therapist each see a different navigation set over the same underlying facts, rather than one menu with items hidden by permission.

---

## 3 · The operational spine

The consultation lifecycle, end to end. Each arrow is a state transition that the system enforces rather than merely records.

```
  Enquiry received
        │
        ▼
  ┌───────────────┐   referral record created, 8-state machine begins
  │   MATCHING    │   assigned to therapist → accepted or returned
  └───────┬───────┘
          │ accepted
          ▼
  ┌───────────────┐   room + therapist + time reserved
  │ FIRST VISIT   │   entitlement reserved if institutionally funded
  │   BOOKED      │
  └───────┬───────┘
          │ client arrives — reception presses "arrived"
          ▼
  ┌───────────────────────────────────────────────────┐
  │  COUNTER SEQUENCE (one step visible at a time)    │
  │   1. Attendance  → arrived / did not attend       │
  │   2. Collection  → amount, method, discount       │
  │   3. Receipt     → fee item, number, print        │
  └───────┬───────────────────────────────────────────┘
          │ identity data completed
          ▼
  ┌───────────────┐   permanent case number assigned
  │  ACTIVE CASE  │   entitlement moves reserved → consumed
  └───────┬───────┘
          │
          ├──────────── recurring sessions ─────────────┐
          │              (book → attend → collect)      │
          │                                             │
          │   if institutionally funded:                │
          │   charges accumulate into a claim container │
          │   → submitted → settled → received          │
          │                                             │
          ▼                                             │
  ┌───────────────┐                                     │
  │    CLOSED     │ ◄───────────────────────────────────┘
  └───────┬───────┘  entitlements closed with the case
          │
          ▼
     may be reopened
```

### The governing principle: attendance drives the record

The single most consequential design decision in the system is that **a billable session comes into existence when reception presses "arrived" — not when the appointment's scheduled time passes.**

This was not the original behaviour. Version 1 materialised sessions by elapsed time: any booked appointment whose end time had passed became a billable session automatically, and institutional entitlement was consumed at that moment. Because there was no scheduler, the trigger was *opening the ledger page* — meaning that merely viewing a screen consumed clients' funded session allowances.

The replacement is explicit and auditable: a session record exists if and only if someone marked attendance. A client who did not attend produces no charge; their reserved entitlement returns. The time-based materialiser was not deleted but retained as a back-dating tool for the case where reception forgets, and it is no longer reachable from any read path.

---

## 4 · Domain model overview

Entities grouped by the concern they serve.

### Identity and relationships

| Entity | Role |
|---|---|
| `users` | Staff and therapists. Carries role, unique user code, and commission rate |
| `cases` | A client. Two-stage identity (see §5.4). Carries funding source, assigned therapist, billing cycle, case type |
| `couple_members` | Links a couple case to its two individual member cases |
| `institutions` | Funding bodies, identified by a five-character code |
| `invitations` | Role-bearing registration and reset keys |

### Scheduling

| Entity | Role |
|---|---|
| `appointments` | A scheduled session. Carries room, therapist, time range, modality, consult type, attendance state, pricing snapshot |
| `appointment_admin_tasks` | Per-appointment administrative checklist items, copied from the plan's checklist at booking |
| `rooms` | The room master: twelve rooms across three floors |
| `venue_rentals` | Space let to an outside party with no clinical session |
| `hall_bookings` | Fifth-floor hall events, with separate setup and event periods |

### Clinical and intake

| Entity | Role |
|---|---|
| `referrals` | Pre-case intake record and the matching state machine |
| `session_records` | The session as a financial fact. See §7.1 |

### Money

| Entity | Role |
|---|---|
| `session_records` | Consultation charges — the de facto consultation ledger |
| `receipts` | Issued receipts, with void and reprint history |
| `fee_items` | The receipt line-item master |
| `invoices` | Grouped billing documents |
| `claim_batches` | Legacy claim container (self-pay and legacy institutional) |
| `therapist_payouts`, `payout_details` | Monthly compensation and its constituent sessions |
| `petty_cash` | Operating expenses, tracked as a running balance |
| `product_sales` | Incidental merchandise, with its own receipt sequence |

### Institutional funding subsystem (prefix `inst_`)

| Entity | Role |
|---|---|
| `inst_contracts` | A contract with a funding body |
| `inst_plans` | A plan within a contract: pricing, entitlement, claim and receipt rules |
| `inst_rate_rules` | Ordered pricing rules; first match wins |
| `inst_quota_pools` | Contract-level shared entitlement, measured in sessions or in currency |
| `inst_enrollments` | One client's entitlement state under one plan |
| `inst_claim_cases`, `inst_claim_lines` | Claim container and its member charges |

### Infrastructure

| Entity | Role |
|---|---|
| `number_sequences` | Atomic identifier allocation across all numbering schemes |
| `audit_log` | Complete before and after state for every mutation |
| `notifications` | In-application alerts raised as side effects of domain events |
| `quota_templates` | Reusable entitlement configurations |

---

## 5 · The consultation pipeline

### 5.1 Intake and matching

An enquiry becomes a `referral` — a staging record that exists only until a formal case is created. It captures presenting issues, preferred times, modality, referral source, any requested therapist, and a suspected funding body (advisory only; the actual plan is chosen at booking).

The matching state machine has eight states:

| State | Meaning |
|---|---|
| `new` | Intake form recorded, not yet assigned |
| `matching` | Assigned to a therapist, awaiting response |
| `unmatched` | Nobody accepted, or the response window expired; may be reassigned |
| `accepted` | A therapist accepted and offered times; reception may now book |
| `booked` | A first-visit appointment exists, awaiting arrival |
| `converted` | The client attended and a formal case now exists; leaves the list |
| `cancelled` | Withdrawn by the client or by reception, with a reason |
| `closed` | Ended for another reason, such as repeated non-attendance |

Two of these states carry enforced integrity conditions, because both can be silently broken by editing an appointment outside the referral service:

- `booked` requires a live appointment that exists, is still booked, and has not yet been attended. Without this, the referral stalls permanently and the client never receives a case number.
- `converted` requires a case that exists, is active, and holds a case number — because that is what "converted" means.

A referral source of "introduced by a friend or relative" raises a dual-relationship prompt, reflecting professional practice requirements.

### 5.2 Scheduling

An appointment is created time-first: reception picks a time, and the system offers the rooms and therapists free at that time. This reverses version 1's room-first form, which required the operator to already know what was available.

The appointment carries three orthogonal descriptors, each of which affects pricing:

| Descriptor | Values | Meaning |
|---|---|---|
| `session_type` | `in_person`, `online`, `outdoor` | The delivery modality. Determines whether a room is required and whether the outcall minimum applies |
| `consult_type` | `individual`, `couple`, `family`, `parenting` | The therapeutic format |
| `location_kind` | `clinic`, and others per contract | Where it happens, for contracts that price by location |

`consult_type` was added because two funded plans price by therapeutic format — individual at one rate, parenting at another, family at a third, all delivered in person. Before it existed, those plans had no dimension to price against and **returned zero for every session**. The existing `session_type` could not be reused: its values already carry operational meaning elsewhere.

Batch booking creates a recurring series — weekly or fortnightly — as one operation, with each occurrence individually conflict-checked and individually priced.

### 5.3 Attendance and session creation

Marking attendance is the pivot of the entire financial chain.

| Attendance state | Effect |
|---|---|
| `pending` | Scheduled, not yet resolved. The default |
| `arrived` | A session record is created. Institutional entitlement moves from booked to consumed. The charge enters the day's takings |
| `no_show` | No consultation charge. Reserved entitlement is returned. A no-show fee charge may be raised if the plan provides for one |

Non-attendance requires a reason from a fixed set — client leave, last-minute cancellation, unreachable, other — plus an optional follow-up method, because the clinic's collection practice differs by reason.

Session duration may be adjusted after the fact when a session ran long or short. Doing so rewrites the appointment's time range (so the calendar never disagrees with what was charged), re-checks the adjusted period against neighbouring bookings, re-prices the session, and **re-synchronises the contract-level entitlement pool with the difference**. That last step is easy to forget and produces an error visible only when a pool approaches exhaustion.

### 5.4 The counter sequence

Reception performs three steps, and **only one is visible at a time**. This is deliberate: it prevents a half-completed transaction from leaving inconsistent data if the operator is interrupted.

| Step | Captures | Precondition |
|---|---|---|
| 1 · Attendance | Arrived or did not attend; reason if not | Appointment is pending |
| 2 · Collection | Amount due, method (cash or transfer), discount and note, transfer reference, duration adjustment | Attendance recorded as arrived |
| 3 · Receipt | Fee item (from the master, or free text), amount, note | Payment recorded |

Step 3 is gated at the API: issuing a receipt against an unpaid charge is rejected. The same condition is asserted as a standing data check, so that no path which bypasses the endpoint can create a receipt for money not received.

Each step is independently idempotent, and the step to display is derived from the combination of attendance state, payment state and receipt existence — not stored as a separate progress field that could drift.

### 5.5 Case lifecycle and two-stage identity

A case acquires its identity in two stages, because reception cannot always obtain full identification at first contact:

| Stage | Identifier | Requirements | Capability |
|---|---|---|---|
| **Provisional** | A temporary sequence number | Name and basic details | One first-visit appointment |
| **Active** | An eight-digit case number | National identification number, date of birth, address, emergency contact | Recurring sessions, institutional claims |

Activation is the transition, and it is enforced in both directions: a case with a number cannot be provisional, and an active or closed case must have a number.

There is a further condition on the institutional side: **a client whose institutional entitlement has been consumed must hold a permanent case number.** Claims are made against identified individuals, so consuming entitlement for an unidentified client would create a charge that can never be claimed.

**A failure here was found in live use.** The first-visit form asked for a different set of fields than activation required, so reception would complete the form, press "convert", and be told that a date of birth was still needed. The form now derives its required fields from the activation rule itself, and a test asserts the two lists are identical rather than merely checking that the endpoint responds.

**Closure** sets the case inactive and closes its institutional enrolments, releasing entitlement that would otherwise remain locked against a client who has left. Cases may be reopened.

### 5.6 Couple cases

A couple is modelled as **its own case** that owns the joint appointment and its billing, while both individuals remain full independent cases, linked by membership.

This arrangement was chosen because the entire billing, ledger, claim, settlement and compensation chain is scoped to a case. Representing the couple as a case lets it flow through all of that unchanged, and counts as exactly one intake, equal to any other case.

Institutional funding creates the complication. Institutional claims are **per person** — they require that individual's identification and draw on that individual's entitlement — and a couple case has no personal identity. The resolution is that a joint appointment nominates a **paying party** at booking: the couple case itself (self-pay, combined) or either member (that member's institutional entitlement). Entitlement, visit sequence and billing all follow the paying party, so per-person claiming remains correct with no special handling. The treating therapist is always taken from the couple case, since a member's own therapist may differ.

A couple case must have exactly two members, and this is asserted as a standing check.

---

## 6 · Institutional funding subsystem

### 6.1 Why it is a subsystem, and the dependency rule

The clinic's 54 funded plans vary along more dimensions than any single pricing table can express. Rather than add fields to the core model for each variation, all of it is contained in one subsystem behind a narrow interface.

**The dependency rule is one-directional and absolute:** the core system defines the interface; the subsystem implements it. Core code never references the subsystem. The subsystem freely references core entities, because that direction is permitted.

The acceptance criterion was stated concretely and remains testable: **remove the subsystem entirely and the core system still runs**, degrading to a self-pay-only clinic because no provider is registered.

The interface is eight methods — three queries without side effects, five commands which must participate in the caller's database transaction:

| Method | Kind | Purpose |
|---|---|---|
| `list_eligible_plans` | Query | Which plans a client may use on a given date |
| `quote` | Query | Full pricing snapshot for a set of circumstances. Writes nothing |
| `get_case_enrollments` | Query | A client's complete entitlement state |
| `enroll` | Command | Add a client to a plan |
| `reserve` | Command | Booking: move entitlement to reserved |
| `consume` | Command | Attendance: move reserved to consumed |
| `resync_consumed` | Command | A charge changed after the fact; adjust the pool by the difference |
| `release` | Command | Cancellation or non-attendance: return entitlement |

The commands must be transactional with the caller because entitlement arithmetic cannot tolerate partial completion. This is the principal reason the subsystem is a module within one application rather than a separate service.

The interface is deliberately **not** named for institutions. Insurance reimbursement or a corporate assistance programme would be an additional implementation, with no change to the interface or to any caller.

### 6.2 Three layers

| Layer | Content | Stability |
|---|---|---|
| **1 · Primitives** | Entitlement, rate rules, claim containers | Stable; shared by every plan |
| **2 · Pricing snapshot** | The answer computed at booking, stored on the appointment and copied to the session record | Immutable once written |
| **3 · Contract modules** | Per-contract assembly and presentation | Changes with each contract |

Layer 3 currently holds five dedicated modules — the municipal health bureau plan, the military care programme, the city personnel office plan, the education support centre plan, and the venue-letting arrangement — plus a generic module and a count-based claim module. Every other plan uses the generic module and can be promoted to a dedicated one later without migration.

The five dedicated modules are selected by contract name. **Renaming one of those contracts silently downgrades it to the generic module**, which is a known fragility.

### 6.3 The pricing snapshot

The core system stores **the answer, not the inputs**: unit price, client portion, institution portion, compensation mode, commissionable base, and the complete quote as structured data.

The reason is that historical amounts are facts. When a contract's rates change, sessions already delivered must not change value. A system that recomputes historical prices from current rules cannot produce a defensible financial record.

This principle is applied consistently: quotes are snapshots, and paid compensation is likewise never recalculated. It is the discipline that makes the financial record auditable.

Snapshots are copied **twice** — once onto the appointment at booking, then again onto the session record at attendance. The session record is the row that reaches reports and claims, so the snapshot must travel with it; the appointment may subsequently be edited or cancelled, while a session record, once created, does not change.

### 6.4 Entitlement: a three-state model

Each enrolment tracks entitlement in three states, and they must always balance:

```
quota_limit + extended  ==  used + reserved + booked
```

where `booked` is not stored but counted live from appointments that are booked and not marked as non-attendance.

This identity is checked continuously. Any imbalance means some path consumed entitlement without returning it, and the three-colour progress bars on the contract panels would drift further out of true with every occurrence.

Five distinct defects were found and corrected against this identity: cancellation not returning entitlement; non-attendance counted twice; closure not closing enrolments; the contract pool incrementing but never decrementing; and after-the-fact duration changes not adjusting the pool.

Entitlement comes in two tiers, which combine:

- **Per-client entitlement** on the enrolment — the individual's allowance under the plan
- **Contract-level pools** — a shared allowance measured either in sessions or in currency. One plan carries an annual monetary pool; the pool's remaining balance is the binding constraint regardless of individual allowances

Extensions are tracked separately, with the approver and approval time recorded, because an extension is a decision someone made rather than a property of the plan.

### 6.5 Ordered rate rules

Pricing is an ordered list of rules per plan. Each rule has a condition; evaluation proceeds in order and **the first match wins**. A final rule without conditions acts as the default.

Conditions may test seven dimensions: visit sequence, consult type, session type, location kind, duration, sub-unit, and time band. This expresses the real contract register: tiered pricing by visit number, pricing by therapeutic format, pricing by therapist, monetary pools, rebate arrangements, periodic sub-limits, and base-plus-extension structures.

A condition key the pricing engine does not recognise is **skipped permissively**, which means a mistyped key turns its rule into one that matches everything — producing a wrong price with no error. This is guarded by a standing check asserting that every condition key in every stored rule is one the engine knows.

A rule editor exists, built late because it was the one component with no reference design. Building it revealed two faults: existing plans' rates could not be edited at all, and plan creation accepted only a single condition — so the two plans priced by therapeutic format had no way to enter their rates.

### 6.6 Compensation modes

Three modes, with materially different money flows:

| Mode | Flow | Effect on compensation |
|---|---|---|
| `commission` | The clinic collects in full and shares with the therapist by rate | Positive line |
| `kickback` | The therapist collects directly and owes the clinic a share | **Negative line** — a deduction, and the receipt is not clinic cash income |
| `none` | No therapeutic labour, such as venue letting | Excluded entirely |

Compensation is generated monthly and is idempotent: it may be re-run, skipping already-paid months and recalculating only pending ones. The total must equal the sum of member sessions — void sessions excluded, rebates negative, discounts deducted from the base — **less venue fees owed by that therapist for private room use that month**.

That final deduction was absent. Documentation described it as a display omission; it was in fact money never deducted, amounting to a five-figure discrepancy in the test data. The fault was duplicated: the data generator had copied the compensation calculation rather than calling it, so the copy was missing the same term.

### 6.7 Claim lifecycle

A claim case is a **container**. Its capacity is an upper bound, not a gate: a partially filled container may still be submitted, and whatever was not collected is handled by a reminder — including a cross-month reminder for charges left behind.

Grouping follows the plan: by period, or by accumulated case count where the container closes automatically on reaching capacity.

The implemented state sequence is:

```
collecting ──► submitted ──► closed
     │
     └──► void   (members' payment status reverts to unpaid)
```

Two gates precede submission where the plan requires documentation: the therapist confirms their materials, then reception verifies them. Returning a claim for correction **clears both gates** and records the reason, because a returned claim must be re-verified rather than resumed.

> **Known inconsistency.** The model's inline comment describes a five-state sequence including `ready` and `received`. Those two values are not used anywhere in the subsystem; `ready` appears only as a computed boolean indicating that a count-based container has reached capacity. The comment is stale. The legacy `claim_batches` mechanism does use `ready` and `received` — see §7.3.

---

## 7 · Money

### 7.1 Session records: the consultation ledger

`session_records` is the system's financial record of delivered therapy. One row per attended appointment, created at attendance, and thereafter immutable in substance.

It carries the recognition date in clinic local time, the amount, the client and institution portions, the discount, the compensation mode and commissionable base, the collection state, the receipt number, the pricing snapshot, void status, and the outcall minimum supplement.

Two properties matter structurally:

- **Recognition date is the appointment's start date in local time.** Asserted as a standing check, because a path computing it in UTC would move late-evening sessions to the previous day and break daily reconciliation by exactly one day's worth of charges.
- **Collection state and claim state are separate fields.** `payment_status` tracks the institutional claim's progress; a separate set of fields tracks whether the client's own portion was collected at the counter. Sharing one field was rejected: the two have different meanings and conflating them would break the claim flow.

### 7.2 Receipts and fee items

Receipts reference the charge they evidence. They carry a fee item from the master or free text, a status of issued or void, and void reason, time and actor. Reprints reuse the base number with a new row, which yields a reprint trail without mutating the original.

Four receipt formats are produced as documents: single session, multi-session, institutional, and merchandise.

Receipt numbers must be unique **across two tables** — session records and receipts each hold one — which no single table constraint can express. A standing check asserts uniqueness over the union. The check exists because the structure permits a collision: earlier code counted existing rows separately in each table and could issue the same string twice on the same day.

### 7.3 Two parallel claim mechanisms

The system contains **two claim implementations at once**:

| Mechanism | Scope | State sequence |
|---|---|---|
| `claim_batches` (legacy) | Self-pay settlement and legacy institutional claims | `collecting → ready → submitted → received` |
| `inst_claim_cases` | The institutional subsystem | `collecting → submitted → closed`, plus `void` |

Document 09 identified this duplication and ruled that they must be merged. The new mechanism was built; the old one still runs. Both are reachable, and they use different vocabularies for comparable states.

### 7.4 Other money

| Record | Structure | Note |
|---|---|---|
| Venue fees | An amount and a payer on the rental record | Not a ledger row; no receipt |
| Hall events | A lecturer fee and a flag for whether it reaches the clinic account | Not a ledger row; no receipt |
| Merchandise | Its own table with its **own receipt sequence** | Separate numbering space |
| Petty cash | A running balance per entry | A different pattern from charge rows |

The consequence is that there is no single place from which total daily income can be computed. This is the central finding of document 16.

### 7.5 Supervision fee modes

Venue lettings for supervision follow one of two arrangements, with completely different accounting:

| Mode | Arrangement | Venue fee |
|---|---|---|
| **A** | Reception collects the supervision fee and issues the receipt | **Must be zero** — otherwise the therapist is charged twice |
| **B** | The therapist collects directly | Recovered from that month's compensation |

Mode A's zero fee is asserted as a standing check.

---

## 8 · Space and scheduling resources

### 8.1 Three occupancy models

| Occupier | Structure | Protection |
|---|---|---|
| Appointments | Room and time range | Database exclusion constraint, within the table |
| Venue rentals | Room and time range | Database exclusion constraint, within the table |
| Hall bookings | **No room field** — event period and optional setup period | Separate exclusion constraint on event period |

### 8.2 Three layers of enforcement

For rooms, protection is deliberately layered:

1. **Database constraints** prevent overlap within each table absolutely.
2. **An application module** checks across the two room-holding tables and reports *which* booking conflicts, so reception receives an actionable message. Cross-table overlap cannot be expressed as a single database constraint, since exclusion constraints apply to one table.
3. **A standing check** verifies that cross-table overlap has not occurred, as a backstop run with every data generation and in continuous integration.

This arrangement — absolute guarantee below, comprehensible message above, independent verification alongside — is the pattern the system uses wherever a rule cannot be expressed in one place.

### 8.3 Known gap: therapists are not conflict-checked

**No check anywhere prevents a therapist from being scheduled twice at the same time.** Not in the database, not in the application. A therapist may be booked for an in-person session in room 2A at 14:00, an online session at 14:00, and an outreach visit at 14:00, and the system will accept all three.

This was identified in August 2026 as one of eight architecture-level conflicts and remains open. It is the first item in document 16's sequencing, because a therapist's time is a fixed resource exactly as a room is, and the current model has no place to express that.

### 8.4 Additional scheduling attributes

| Attribute | Purpose |
|---|---|
| Actual start and end | Duration adjustment; rewrites the time range and re-prices |
| Video link and forwarded timestamp | Online sessions; "awaiting send" and "sent" are distinct operational states |
| Leave | Client-initiated absence, distinct from non-attendance |
| Administrative checklist | Per-appointment tasks copied from the plan, each requiring an actor and timestamp when completed |

---

## 9 · Identifiers and numbering

All identifiers are allocated from a single sequence table using one atomic statement. This replaced counting existing rows and adding one, which was unsafe under concurrency, re-issued numbers after deletions, and — in one specific path — allocated the receipt number before the row was written, so several charges on one day could receive the same number and collide.

Seven sequence scopes exist, each keyed to include its date or year where the format requires:

| Scope | Format |
|---|---|
| Case | Year-based, eight digits |
| Couple case | Year plus sequence |
| Appointment | Date plus therapist code plus sequence |
| Receipt | Date plus category plus sequence |
| Merchandise | Date plus sequence |
| Venue rental | Date plus sequence |
| Referral | Prefix plus sequence |

Two standing checks guard the scheme: an appointment number's date segment must equal the appointment's local start date, and receipt numbers must be unique across the two tables that hold them.

The allocator takes an explicit date rather than reading the clock, so historical data receives period-correct numbers.

---

## 10 · Reporting

Three groups, each defaulting to the current month on open:

**Operational** — intake statistics with a separate breakdown for clients who requested a specific therapist, and spreadsheet export; room utilisation; caseload per therapist.

**Financial** — monthly profit and loss; attrition warning, computed live from each case's days since last appointment rather than from a stored status field.

**Charts** — nine switchable charts, each exportable as an image.

The attrition report was rewritten after a performance measurement: it had executed one query per case and parsed time ranges as strings with errors suppressed. The replacement is a single aggregate query, reducing a representative run from 0.56 seconds to 0.019 seconds — a difference that only became visible once the test data reached realistic volume.

---

## 11 · The correctness regime

This section describes what makes the system maintainable, and is the part most often absent from comparable systems.

### 11.1 Three independent layers

| Layer | Count | Question answered |
|---|---|---|
| **Automated tests** | 251 across 24 files | Does each behaviour work? |
| **Cross-table invariants** | 25 | Does the data satisfy the rules that must always hold? |
| **Coverage checks** | 76 | Has each rule actually been exercised by data? |

They are independent because they fail for different reasons. Tests verify a path. Invariants verify the whole dataset arithmetically — a test can pass while an invariant breaks, if some other path corrupts the data. Coverage verifies that an invariant was actually tested against real cases: an invariant over an empty set passes trivially.

### 11.2 Invariants

Twenty-five assertions, each a single query returning offending rows. Any row returned is a failure.

| Area | Assertions |
|---|---|
| Entitlement | Three-state identity balances; contract pool equals the sum of its delivered, non-void charges; a closed case has no live enrolment |
| Sessions | Recognition date equals the local start date; attendance implies a session record; non-attendance and cancellation produce no consultation charge |
| Space | No room overlap across appointments and rentals; no hall overlap; adjusted actual times match the appointment's range; mode A supervision carries no venue fee |
| Checklists | A completed task has both actor and timestamp |
| Money | Receipt numbers unique across both tables; no receipt without payment; client portion plus institution portion equals the total; a funded session is never priced at zero except where the plan permits it |
| Claims | A charge belongs to at most one claim, and a claimed charge is not void; a submitted claim's members carry the matching payment state |
| Compensation | Pending compensation equals the computed total, net of venue recovery. Paid months are excluded deliberately — they are historical fact |
| Identity | Case number if and only if active or closed; consumed entitlement implies a case number; a couple has exactly two members |
| Pricing | Every stored rate-rule condition key is one the engine recognises |
| Matching | A booked referral has a live unattended appointment; a converted referral has an active, numbered case |

**One invariant was itself wrong.** The attrition check queried a status value the backend never writes. A check querying a non-existent field fails permanently and pressures the team to invent a fictitious status to satisfy it. The check was corrected, not the data.

### 11.3 Coverage checks

Seventy-six checks over twelve areas, each setting a minimum number of rows that must exercise a given rule. Their purpose is to answer a question tests cannot: *is there any data in this system that goes down this path?*

The checks encode their own justification. Two examples:

- *Self-pay monthly billing, greyed on attendance alone* — "without samples, an error in this rule would go unnoticed; the first implementation classified monthly cases as outstanding for exactly this reason."
- *Venue fee recovered from compensation* — "this deduction was once never applied at all."

Several thresholds were deliberately set **below** what would look impressive, because a threshold above real operating volume forces the fabrication of data with no real-world counterpart. Online sessions, for instance, are capped at a figure reflecting three to five per week across the whole clinic.

### 11.4 Front-end discipline

Two automated guards:

- **Type checking** across the whole front end, with no errors permitted.
- **A design-token guard** over the entire source tree. It was introduced after measuring 2,178 hard-coded colour values in 116 distinct shades, which is why the interface looked inconsistent. The count is now zero, and the guard prevents regression.

The rule it enforces is that **colour expresses state, never action**. Action controls are neutral; colour is reserved for conditions such as unpaid, not attended, or overdue. Categorical attributes — role, payment type, age band — may not borrow state colours, because a green "Administrator" badge reads as "completed".

Normalising colour exposed two faults invisible to code review: one claim state rendered in four different colours across four pages, and role badges using state colours throughout.

### 11.5 Three recurring failure modes

Recorded in the project's working rules because they account for most defects found:

1. **The documentation already said so, and nobody read it before starting.** All three front-end contracts restate rules already written in documents 01, 02 and 06.
2. **The path that corrupts data is often the most natural one.** The fix is to make the natural path the correct one, not to document a prohibition — and to add a gate so the wrong path fails loudly rather than succeeding quietly.
3. **Duplicated knowledge always diverges.** The specific recurring form is the data generator copying an endpoint's calculation, because the endpoint's safeguards block historical data. The copy is correct only on the day it is written. This caused two money-affecting errors in a single session: compensation missing the venue deduction, and duration changes not adjusting the entitlement pool.

---

## 12 · Application surface

**Back end** — twenty-six routers in the core system, plus one each for the institutional and matching subsystems. Core areas: appointments, cases, ledger, claim batches, receipts, invoices, payouts, petty cash, product sales, reports, attrition, dashboard, notifications, reminders, rooms, room calendar, venues, case quotas, quota templates, fee items, institutions, users and authentication, data import and export, audit, health.

**Front end** — twenty-nine pages, twenty-four within the authenticated shell, organised as seven feature areas: administration, booking, cases, finance, institution, rooms, and shared infrastructure.

Reception works from a room calendar with a half-hour grid and the three-step counter sequence; an operations overview presenting the day as a task queue; a daily report and reconciliation; booking; the appointment register; matching; cases; receivables; and compensation. Therapists see today's schedule, their week, their caseload, booking, assignment invitations, documentation confirmation, their compensation and their statistics.

The interface is built on a shared component library over six semantic state tokens, replacing per-page reinvention of cards, tables and buttons.

---

## 13 · Platform and deployment

| Component | Technology |
|---|---|
| Back end | Python 3.11, FastAPI, SQLAlchemy 2, Alembic migrations, JWT authentication |
| Front end | Next.js 14 App Router, Tailwind CSS, Auth.js v5 |
| Database | PostgreSQL 16, using range types with exclusion constraints for scheduling integrity |
| Local development | Docker Compose |

**Production runs on a clinic-owned Windows machine**, exposed through a Cloudflare tunnel, since 31 August 2026. It was previously hosted on a managed cloud platform. Four deployment pitfalls encountered during that migration are recorded so that they are not re-encountered: a cloud database at a newer major version than the local one, container registry credentials under remote sessions, host trust configuration required behind the tunnel, and container lifecycle across sessions.

A startup health check verifies database connectivity, cross-origin configuration, remote maintenance access, free disk space, front-end dependency completeness, static asset presence, clock synchronisation, and whether the running process is older than the deployed build.

---

## 14 · Known gaps and accepted debt

Stated plainly, because a framework document that omits them is not usable for planning.

### Open gaps

| # | Gap | Consequence |
|---|---|---|
| 1 | **Therapists are not conflict-checked** | One therapist can be booked into three simultaneous commitments |
| 2 | **The fifth-floor hall is outside the shared occupancy check** | Its own schema and constraint; the cross-table module does not see it |
| 3 | **Two claim mechanisms coexist** | Different state vocabularies for comparable states; document 09 ruled they must merge |
| 4 | **Money is held in four unconnected places** | Total daily income cannot be computed from one source; cash-plus-transfer reconciliation has no single left-hand side |
| 5 | **Receipt numbers occupy two sequence spaces** | Guarded by a check rather than prevented structurally; venue and hall fees have no receipt at all |
| 6 | **Tax withheld and transfer fees are netted inside the claim case** | Neither cost reaches any ledger, so the profit and loss statement cannot see them |
| 7 | **Non-therapy counterparties have no identity** | Renters, lecturers and borrowers are free-text fields; course participants have no representation |
| 8 | **Payment method is hard-coded in 21 places** | Adding a payment method requires 21 edits |
| 9 | **Claim amounts have no reconciliation assertion** | Neither "claim total equals sum of members" nor "net received equals claimed less deductions" is checked |
| 10 | **Contract modules dispatch on contract name** | Renaming a contract silently falls back to the generic module |

### Accepted, by decision

| Item | Decision |
|---|---|
| Permissive handling of unknown rate-rule condition keys | Kept, guarded by a standing check rather than made strict |
| Remaining funded plans entered as synthetic data | Transcribing 43 contracts is data entry, and errors would surface only on a wrong invoice. It belongs in a plan-entry interface the clinic operates itself |
| Receipt number format | Implemented as a switchable generator; the final format is not yet settled |
| Daily settlement objects and reconciliation locking; discount on the daily report; charge-void interface | Deliberately deferred under document 09 |
| Four contract-panel blocks not extracted into shared components | Working functionality written inline. Distinguishing "missing feature" from "missing abstraction" matters: the former needs building, the latter only moving |

### Known documentation drift

The claim case model's inline comment describes states the code does not use (§6.7). The architecture notes a Redis cache in the local composition that no application code references.

---

## 15 · Appendix: enumerations

| Field | Values |
|---|---|
| User role | `admin`, `accountant`, `staff`, `therapist` |
| Case status | `initial`, `ongoing`, `closed` |
| Case type | `individual`, `couple` |
| Funding source | `self_pay`, `institution` |
| Billing cycle | `once`, `monthly`, `multiple` |
| Appointment status | `booked`, `executed`, `cancelled` |
| Attendance | `pending`, `arrived`, `no_show` |
| Non-attendance reason | `case_leave`, `last_minute_cancel`, `unreachable`, `other` |
| Session type | `in_person`, `online`, `outdoor` |
| Consult type | `individual`, `couple`, `family`, `parenting` |
| Fee category | `counseling`, `no_show_fee` |
| Payment method | `cash`, `transfer` |
| Payment status | `unpaid`, `paid`, `claiming`, `claimed` |
| Compensation mode | `commission`, `kickback`, `none` |
| Quota unit | sessions, currency |
| Referral status | `new`, `matching`, `unmatched`, `accepted`, `booked`, `converted`, `cancelled`, `closed` |
| Institutional claim status | `collecting`, `submitted`, `closed`, `void` |
| Legacy claim batch status | `collecting`, `ready`, `submitted`, `received` |
| Receipt status | `issued`, `voided` |
| Supervision fee mode | `A`, `B`, or none |
| Rate-rule condition keys | `visit_seq`, `consult_type`, `session_type`, `location_kind`, `duration_min`, `sub_unit`, `time_band` |

---

*CheerPsy · Document 17 · Operational System Framework (as built) · 17 November 2026*
*Companion to document 16, which proposes restructuring this baseline. Structural claims verified against the source tree on 17 November 2026.*
