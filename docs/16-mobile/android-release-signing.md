VISTAAR — Android Release Signing

Date: 2026-09-03
Status: Real production keystore generated and verified working — see
§4 for what "verified" actually means here. Not yet backed up anywhere
but this one machine — see §3, the single most important section in
this document.

1. What was done

Resolves `app-store-submission-checklist.md` §6's `[NEED]` — a real
release build was previously signed with the Flutter template's own
debug key (`android/app/build.gradle.kts` pointed `signingConfig` at
`signingConfigs.getByName("debug")`), which Google Play would reject
for a real submission.

Generated a real, production-grade Android signing keystore:

- **Algorithm**: RSA 2048-bit, self-signed, `SHA384withRSA`.
- **Format**: PKCS12 (`keytool`'s current default — not the older JKS
  format; PKCS12 requires the store password and key password to be
  the *same* value, which the generated `key.properties` reflects).
- **Validity**: 10,000 days (~27 years) from 2026-09-03 — Google's own
  documented recommendation is at least 25 years, since this exact key
  must sign every future update to this app for its entire lifetime on
  Play Store.
- **Alias**: `vistaar-release`.
- **Distinguished Name**: `CN=VISTAAR, OU=VISTAAR, O=VISTAAR,
  L=Unknown, ST=Unknown, C=IN`. Deliberately generic, not a fabricated
  legal entity — written before the owner's 2026-09-03 decision that
  VISTAAR publishes through a Company/Organization Google Play Console
  account (`app-store-submission-checklist.md` §1); inventing a
  specific organization name here would have been guessing ahead of
  that decision. Not regenerated now that the decision exists: the DN
  has no functional effect on how Play Store treats the app (it
  doesn't validate identity against it, and Google's own organization-
  account verification runs through a separate D-U-N-S-based process,
  not this certificate) — regenerating with a more specific DN remains
  possible any time up until the first real Play Store upload, after
  which the key itself (not the DN) is what must never change.
- **SHA-256 certificate fingerprint**:
  `36:9A:55:78:0E:62:B6:DD:2F:94:23:77:54:58:83:93:F8:2F:A9:42:C3:76:F5:42:11:09:42:B5:25:DC:8A:7A`
  — this is not secret (it's meant to be shared — Google Play's own
  App Signing setup, Firebase SHA-256 registration for Dynamic Links/
  App Links/Google Sign-In all ask for exactly this value), unlike the
  keystore file and its passwords, which are.

2. Where everything actually lives

- **The keystore file itself**:
  `C:\Users\kumar\Downloads\VISTAAR-Secrets\vistaar-release-key.jks` —
  outside the git repository entirely (not merely gitignored — never
  inside the repo directory tree at all), the same "secrets live in
  VISTAAR-Secrets, not in the repo" pattern already established this
  session for the Firebase service-account credentials file.
- **The passwords + alias + path**:
  `apps/mobile/android/key.properties` — gitignored (already covered by
  Flutter's own default `apps/mobile/android/.gitignore`, which lists
  `key.properties`, `**/*.keystore`, and `**/*.jks` by default; verified
  directly with `git check-ignore`, not assumed). A generated,
  cryptographically-random 32-character password protects the keystore
  — not printed in this document or in any chat output, per standing
  practice for this project. `apps/mobile/android/key.properties.example`
  is the committed template documenting the file's shape without real
  values, matching this project's own `.env.example` convention.
- **The Gradle wiring**: `apps/mobile/android/app/build.gradle.kts` —
  loads `key.properties` conditionally (`rootProject.file("key.properties")`).
  If present, the `release` build type signs with it for real; if
  absent (any other developer's checkout, or CI without the real file),
  it falls back to the debug key, exactly matching Flutter's own
  default template behavior — a checkout without the real secrets can
  still run `flutter build`/`flutter run --release`, it just won't
  produce a Play-Store-uploadable artifact.

3. You must back this up yourself — this is the single most important
   paragraph in this document

**This keystore exists, right now, in exactly one place: this one
Windows machine's local disk.** Nothing in this session copied it
anywhere else, and nothing about this environment guarantees it will
still be there tomorrow. `app-store-submission-checklist.md` already
named the stakes precisely: **losing this file, or its password, after
the first real Play Store publish makes every future update to this
app impossible under its current identity** — not "difficult,"
*impossible*; Play Store has no recovery mechanism for a lost upload
key outside a narrow, Google-mediated key-reset process that isn't
guaranteed to succeed.

Before treating this as done, copy both of the following to at least
one durable, independent location (a password manager's file-attachment
feature, an encrypted cloud backup, a hardware security key/offline
drive stored separately from this machine — any of these, not
necessarily all):

- `C:\Users\kumar\Downloads\VISTAAR-Secrets\vistaar-release-key.jks`
- `apps\mobile\android\key.properties` (or just the password inside it
  — but the keystore file itself is the part that can never be
  regenerated if lost; the password alone is useless without it, and
  vice versa)

This document cannot verify you've done this — it can only tell you,
as plainly as possible, that it has not been done automatically by
anything in this session.

4. What "verified" actually means here

Built a real signed release APK end to end and independently confirmed
it — not merely reviewed by reading:

```
flutter build apk --release
```

succeeded (`build/app/outputs/flutter-apk/app-release.apk`, 52.7MB),
and

```
apksigner verify --print-certs app-release.apk
```

(Android SDK build-tools, not `keytool` — modern Android Gradle Plugin
signs with APK Signature Scheme v2/v3, which `keytool -printcert
-jarfile` cannot read; this was tried first and failed with "Not a
signed jar file" before switching to the correct tool) confirmed the
APK's actual embedded signing certificate has the **exact same SHA-256
digest** as the keystore itself — proving the release build is
genuinely signed with the real production key, not silently still
falling back to the debug key. Not verified: an actual upload to Google
Play Console (no developer account exists yet — `app-store-submission-
checklist.md` §1's own `[NEED]`) or Play App Signing's own additional
key-wrapping step, which only becomes relevant at first real upload.

5. What this does not do

- Does not create a Google Play Console developer account or upload
  anything — `app-store-submission-checklist.md` §1's `[NEED]` items
  remain open (now including a real D-U-N-S number, required for the
  Company/Organization account type decided 2026-09-03).
- The publishing-entity decision (individual vs. company) this
  document originally deferred is resolved — Company/Organization,
  2026-09-03 — but did not require touching this keystore at all (§1
  above explains why).
- Does not touch iOS signing in any way — correctly on hold per
  standing instruction.
- Does not back the keystore up anywhere beyond this one machine — see
  §3. This is real, unfinished work only the owner can complete.
