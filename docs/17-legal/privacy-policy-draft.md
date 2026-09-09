VISTAAR — Privacy Policy (DRAFT)

Date: 2026-09-02
Status: **DRAFT — NOT LEGAL ADVICE, NOT READY TO PUBLISH.** Written by
Claude Code, grounded in what the real VISTAAR codebase actually
collects and does (checked directly against the mobile app's permission
declarations, the backend's data model, and `security.md`) — not
boilerplate. It has not been reviewed by a lawyer and must be before it
is shown to a single real user. India's Digital Personal Data Protection
Act, 2023 (DPDP Act) is the relevant framework given VISTAAR's
India-only user base (INR currency, India-based phone numbers) — it has
requirements (a Grievance Officer, specific consent-notice language,
data-principal rights procedures) this draft does not attempt to
certify compliance with; that requires real counsel.

This document intentionally does not invent a company name, registered
address, incorporation details, or a Grievance Officer's contact
information — those are business facts, not something to guess at.
Placeholders are marked `[NEEDS: ...]`.

---

**Privacy Policy**

Last updated: [NEEDS: publish date]

This Privacy Policy explains what information VISTAAR ("we", "us",
"the App") collects when you use the VISTAAR mobile app, as a User
(rider) or a Sarthi (driver), and how it's used.

**1. Information we collect**

*Account & identity*
- Your phone number, used to create your account and sign you in via a
  one-time password (OTP). The OTP itself is never stored in plain text
  longer than needed to verify it, and is never included in your
  account history.
- For Sarthi (driver) accounts: your full name, and the KYC documents
  you submit for verification (government ID, driving license, vehicle
  registration certificate, insurance) — required to let you drive on
  the platform. [NEEDS: confirm final KYC document list and any
  additional identity-verification provider, if one is ever added —
  none exists in the app today; documents are reviewed by VISTAAR's own
  admin team.]

*Location*
- While the app is in use, we collect your device's location to match
  Users with nearby Sarthis, show ride progress, and verify pickup/
  drop-off arrival. We do not collect your location when the app is
  closed or in the background, except for a Sarthi actively online and
  available for rides. [NEEDS: confirm this last clause once/if
  background location for an online Sarthi is ever built — as of this
  policy's drafting, only foreground ("when in use") location is
  requested anywhere in the app.]

*Contacts (only if you use "Book for Someone Else")*
- If you choose to book a ride for someone else, the app can open your
  phone's own native contact picker so you can select who the ride is
  for. We only ever receive the one contact you pick — their name and
  phone number — to pre-fill the booking form. The app never reads,
  uploads, or stores your full contact list, and Contacts access is
  only ever requested at the moment you tap "Choose from Contacts," not
  when you first open the app.

*Ride & financial information*
- Ride history: pickup/drop-off locations, fare, and how you indicated
  you'd pay the driver (cash or UPI) — paid directly to the driver;
  VISTAAR does not process or hold ride-fare payments.
- For Sarthis: wallet balance and transaction history for VISTAAR's own
  platform fees.

*Communications*
- Support messages you send us, and any evidence (photos, videos,
  documents) you submit for a dispute.
- A device push-notification token, so we can send you ride updates.

*Automatically collected*
- Basic technical/error information via our error-monitoring tool,
  configured to exclude your authentication tokens and cookies from
  anything sent to it. [NEEDS: confirm final retention/anonymization
  approach once real error monitoring is active — currently disabled by
  default (no account is provisioned yet).]

**2. How we use your information**

- To create and secure your account, and match Users with Sarthis.
- To calculate fares, verify ride completion, and process VISTAAR's own
  platform fees.
- To review and approve Sarthi documents and vehicles.
- To respond to support requests and investigate disputes.
- To send you ride-related notifications.
- [NEEDS: a decision on whether any data is used for analytics/
  marketing beyond the operational uses above — nothing in the app
  today does this, but this policy should say so explicitly once
  confirmed, not by omission.]

**3. What we don't do**

- We do not sell your personal information.
- We do not read, upload, or sync your phone's address book — only the
  one contact you explicitly choose for "Book for Someone Else."
- We do not process or hold your ride-fare payments — those go directly
  to the Sarthi.

**4. Sharing**

- With the Sarthi assigned to your ride (name, and the location
  information needed to complete the trip) or the User you're driving
  for.
- With service providers who help us run the app: [NEEDS: final list
  once providers are selected — as of this draft: an SMS provider for
  OTP delivery, a push-notification provider (Firebase), and,
  eventually, a payment provider for Sarthi wallet recharge, not yet
  selected].
- With law enforcement or regulators when legally required.
- We do not share your information with advertisers.

**5. Your rights**

Under the DPDP Act, you have rights to access, correct, and request
deletion of your personal data, and to withdraw consent. [NEEDS: the
actual procedure for exercising these rights — who to contact, expected
response time — must be filled in by whoever is designated as VISTAAR's
Grievance Officer, a role the DPDP Act requires and this draft cannot
assign.]

**6. Data retention**

[NEEDS: a real retention policy. `security.md` §58 (location) and §16
(dispute evidence) both explicitly leave exact retention periods as an
unresolved configuration decision, not yet approved anywhere in this
project — this policy cannot state a real number until that decision is
made.]

**7. Children**

VISTAAR is not intended for use by anyone under 18. [NEEDS: confirm
this is the intended minimum age and any related verification
approach.]

**8. Changes to this policy**

We'll notify you of material changes before they take effect. [NEEDS:
confirm notification method — in-app, SMS, or both.]

**9. Contact us**

[NEEDS: Grievance Officer name, email, and postal address — a legal
requirement under the DPDP Act, not optional, and not something this
draft can supply.]

---

**Before this can be published**: legal review (India DPDP Act
compliance specifically), a designated Grievance Officer, a real data
retention policy, and confirmation of every `[NEEDS: ...]` marker above.
