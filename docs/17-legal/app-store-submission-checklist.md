VISTAAR — App Store / Play Store Submission Checklist

Date: 2026-09-02
Purpose: everything genuinely required to publish VISTAAR to Google Play
and the Apple App Store, checked against what actually exists in
`apps/mobile` today — not a generic template. Items are marked **[HAVE]**
(exists/decided), **[NEED]** (a concrete missing asset/account/decision),
or **[BLOCKED]** (needs something else on this list, or outside this
project, first).

This is a checklist to work through, not something I can complete
myself — store accounts, screenshots of a running app on a real device,
and legal documents all need things outside a code editor.

1. Developer accounts

- **[NEED]** A Google Play Console developer account — **[HAVE]**
  decision: Company/Organization account (owner decision, 2026-09-03).
  One-time $25 registration fee, plus, confirmed directly against
  Google's own current Play Console support documentation (not assumed
  from general knowledge — Google requires this specifically for
  organization accounts, separate from and in addition to the $25 fee):
  - A **D-U-N-S number** — mandatory for an organization account
    ("You will not be able to create a developer account for an
    organization without one"). Free from Dun & Bradstreet; Google's
    own Play-Console-specific requests are typically prioritized and
    processed in 1–5 business days (the general D-U-N-S request queue
    can take up to 30 days) — start this lookup early regardless.
  - Organization legal name + address (drawn from a linked Google
    Payments profile), organization phone number, organization
    website, a named contact's name/email/phone, and a separate
    developer email/phone that will be publicly displayed on the Play
    Store listing.
  - Every contact detail is verified via one-time passwords; legal
    name and address are verified before the app can actually publish;
    a verified payment method is required for monetization.
  - Government organizations may qualify for a D-U-N-S exemption by
    contacting Google support directly — not applicable to VISTAAR as
    a private company, noted for completeness only.
- **[NEED]** An Apple Developer Program account ($99/year, needs a
  D-U-N-S number if enrolling as an organization rather than an
  individual — that lookup/registration can itself take days, so this
  is worth starting early). **Still undecided/on hold** — Apple/iOS
  work remains postponed per standing project scope; this Google Play
  decision does not extend to Apple.
- Whether the *same* D-U-N-S number (once obtained) can be reused for
  both Google Play and Apple's own organization enrollment is worth
  confirming directly with Dun & Bradstreet/Apple when that work
  resumes — not assumed here either way.

2. App identity (already fixed in code — do not change without
   understanding the consequences)

- **[HAVE]** iOS Bundle ID: `com.vistaar.vistaarMobile` (confirmed
  directly in `ios/Runner.xcodeproj/project.pbxproj`).
- **[HAVE]** Android application ID: `com.vistaar.vistaar_mobile`
  (confirmed in `android/app/build.gradle.kts`).
- **[NEED]** App display name for each store listing — currently
  "Vistaar Mobile" (`CFBundleDisplayName`) on iOS and "vistaar_mobile"
  (`android:label`) on Android; neither is a polished, final public-
  facing name. Decide the exact public name before submission — this
  is a one-line config change once decided, not a blocker to fix now.

3. Store listing assets — none exist yet

- **[NEED]** App icon — a real, final icon at every required resolution
  for both stores (currently using Flutter's default placeholder
  icon — verified nothing custom exists in
  `android/app/src/main/res/mipmap-*` or `ios/Runner/Assets.xcassets`).
- **[NEED]** Screenshots — both stores require multiple device-size
  screenshots of the actual running app (Play: phone + optionally
  tablet; App Store: multiple iPhone sizes, no simulator-only
  submissions for the final listing though simulator screenshots can
  work for initial review in some cases). Needs a real running app on a
  real or simulated device — the native Contacts-picker and push-
  notification flows specifically need a real device to screenshot
  meaningfully, per the same device limitation already flagged
  elsewhere in this project.
- **[NEED]** Short and long store descriptions, keywords (App Store),
  and category selection (e.g., "Travel" or "Maps & Navigation").
- **[NEED]** A feature graphic (Play Store, 1024×500) and promotional
  text.

4. Privacy & data-safety declarations — depend on the legal documents

- **[BLOCKED]** A published, hosted Privacy Policy URL — both stores
  require this as a live link, not a document in this repo. Blocked on
  `docs/17-legal/privacy-policy-draft.md` being finalized (legal review)
  and hosted somewhere public.
- **[NEED]** Google Play's **Data Safety form** — a structured
  questionnaire about exactly what data is collected and why. Can be
  filled in accurately from what this project already knows for real:
  phone number (account creation), location (approximate + precise,
  "app functionality"), and — only if the Sarthi role's KYC upload is
  in scope for this specific data-safety declaration — identity
  documents. Contacts should be declared too: collected, not shared,
  used only for app functionality (Book for Someone Else), not stored.
- **[NEED]** Apple's **App Privacy ("nutrition label") details** —
  same underlying data, different form. Both forms should be filled in
  together from the same source-of-truth list, to avoid the two stores
  disagreeing about what the app actually does.
- **[NEED]** Confirm whether Google Play's Families/child-safety
  policies apply — likely no (an 18+ ride platform), but this is a
  policy answer within Play Console, not a code question.

5. Permissions justification (both stores review these against the
   actual manifest/Info.plist — already correctly scoped in code, not a
   missing gap, but reviewers will ask about each one)

- **[HAVE]** Location ("when in use" only) — justified by ride
  matching/tracking, already correctly scoped (no background location
  requested anywhere).
- **[HAVE]** Contacts (Android `READ_CONTACTS`, iOS
  `NSContactsUsageDescription`) — justified by Book for Someone Else,
  requested contextually not at launch, already matches both stores'
  stated preference for contextual permission requests.
- **[HAVE]** Notifications (Android `POST_NOTIFICATIONS`, iOS via
  Firebase) — justified by ride status updates.
- **[NEED]** A one-line justification for each, ready to paste into
  either store's review-notes field if asked — the reasoning above is
  accurate and can be reused directly, but hasn't been written up as
  submission-ready copy yet.

6. Build & signing

- **[HAVE, with a real remaining action]** An Android signing keystore
  (release key) — generated 2026-09-03 (ADR-0064,
  `docs/16-mobile/android-release-signing.md`): a real RSA 2048-bit
  PKCS12 keystore, `android/app/build.gradle.kts` now signs real
  release builds with it (verified: built a real release APK and
  independently confirmed its embedded signing certificate matches the
  keystore, via `apksigner verify`, not just reviewed by reading), never
  committed to git. **What's still genuinely open**: the keystore
  currently exists on only one machine — losing it after the first real
  Play Store publish makes future updates impossible without publishing
  as a new app, and it has not yet been backed up anywhere durable and
  independent of that machine. See that document's own §3 for exactly
  what to do. **Not regenerated for the Company/Organization account
  decision above** — the keystore's DN (`O=VISTAAR`, deliberately
  generic, ADR-0064) does not need to match the Play Console account's
  legal entity name; Google's own signing requirements don't tie the
  two together. Nothing to redo here once a real registered business
  name exists — that name only feeds the Play Console account itself
  (§1), not the keystore.
- **[NEED]** iOS code signing — an Apple Distribution certificate and a
  App Store provisioning profile, generated through Xcode/Apple
  Developer portal once the developer account exists (§1). Same
  category of gap as the push-notification/APNs work already flagged:
  needs a real Mac with Xcode, not something this environment can do.
- **[HAVE, Android only]** A first real `flutter build appbundle`/
  `flutter build apk --release` run — done 2026-09-03 (ADR-0064), signed
  with the real keystore above. Still against **dev config** (real API
  base URL not yet set — no real deployed backend exists to point at,
  `deployment-runbook.md`), so not yet a production-config release
  build; that's a separate remaining step once a real backend is
  deployed. iOS (`flutter build ipa`) remains **[NEED]** — needs a real
  Mac, on hold per standing instruction (§9 below).

7. Backend readiness for real users (not a store requirement, but a
   real prerequisite before public release regardless of store
   approval)

- **[BLOCKED]** A real, deployed backend for the app to actually call —
  see `docs/12-deployment/deployment-runbook.md`. A store-approved app
  pointed at nothing real is not a meaningful launch.
- **[BLOCKED]** The payment-related gaps in
  `docs/02-business/known-functional-gaps-2026-09-02.md` — none of them
  block store *approval* itself, but affect what's actually usable once
  real users have the app.

8. Legal documents (beyond the Privacy Policy)

- **[BLOCKED]** Terms of Service — same hosting/legal-review requirement
  as the Privacy Policy; see `docs/17-legal/terms-of-service-draft.md`.
  Apple specifically requires a Terms of Use (EULA) link if the app has
  any user-generated content or subscription — VISTAAR's support
  messages/evidence uploads likely qualify; confirm during submission
  whether Apple's standard EULA suffices or a custom one is required.

9. Review-process realities (not blockers, just worth knowing ahead of
   time)

- Apple App Store review typically takes 1-3 days per submission, can
  reject for reasons requiring a resubmission (common ones for a ride
  app: incomplete permission justifications, a login screen with no way
  for a reviewer to actually test it — VISTAAR will need either real
  demo credentials or a documented test account/OTP bypass path for
  reviewers, which does not exist yet — **[NEED]**).
- Google Play review is typically faster but can flag location/contacts
  permissions for closer manual review given they're sensitive
  categories.

10. Suggested order

1. ~~Decide publishing entity~~ — **decided for Google Play 2026-09-03:
   Company/Organization account.** Start the D-U-N-S lookup now (§1) —
   still the longest lead time in this whole list, 1–5 business days
   for Play Console specifically once requested. Apple's own entity
   decision remains open/on hold (§1).
2. Finalize app name, icon, and get the two legal documents through
   review and hosted (§2, §3, §8).
3. ~~Generate and securely store the Android release keystore (§6).~~
   Generated 2026-09-03 (ADR-0064) — **"securely store" still means
   back it up off this one machine**, see
   `docs/16-mobile/android-release-signing.md` §3.
4. Once a Mac/Xcode is available: iOS signing + the deferred push
   notification setup (§6, cross-referencing the earlier FCM work).
5. Fill in both stores' data-safety/privacy forms from the same source
   list (§4).
6. Take real screenshots on real devices once the above is in place
   (§3).
7. Submit — with a reviewer test-account path ready (§9).
