ADR-0064 — Android Production Release Signing

Status: Accepted — owner instruction ("Prepare Android production
signing using a proper release keystore stored securely and never
committed to Git"), 2026-09-03. Implemented and verified the same day.
Date recorded: 2026-09-03
Deciders: Project owner (explicit written instruction).

1. Decision

Generated a real Android release-signing keystore and wired it into
`apps/mobile/android/app/build.gradle.kts` conditionally — real
production signing when the (gitignored) credentials exist, a graceful
fallback to Flutter's own default debug signing otherwise, so no
checkout without the real secrets ever breaks a build. Full technical
detail — exact algorithm/validity/fingerprint, exactly where every
piece lives, and the real end-to-end verification performed — is in
`docs/16-mobile/android-release-signing.md`, not duplicated here.

2. Why generate a real keystore now, not just prepare the config

Losing a release keystore *after* the first real Play Store publish is
irreversible — `app-store-submission-checklist.md` §6 already flagged
this as a "one-time, high-stakes step." But VISTAAR has never been
submitted anywhere (confirmed directly, not assumed): there is no first
publish yet to make this irreversible today. Generating it now, while a
mistake is still just "generate a different one," is safer than leaving
it as an unstarted `[NEED]` that becomes genuinely dangerous the moment
someone rushes it right before a real submission deadline.

3. Never committed — verified, not assumed

The keystore file itself lives entirely outside the git repository
(`C:\Users\kumar\Downloads\VISTAAR-Secrets\`, the same "real secrets
live outside the repo" location this session already established for
the Firebase service-account credentials). The passwords/alias/path
live in `apps/mobile/android/key.properties`, confirmed gitignored via
a real `git check-ignore` check (not assumed from reading `.gitignore`)
— it turned out Flutter's own default Android project template already
gitignores `key.properties`/`**/*.keystore`/`**/*.jks`, so no new
`.gitignore` entry was even needed. The committed
`key.properties.example` documents the file's shape with placeholder
values only, matching this project's established `.env.example`
convention.

4. What remains genuinely open

- **The keystore is not backed up anywhere except the one machine it
  was generated on.** `android-release-signing.md` §3 is written
  specifically to make this impossible to miss — this ADR does not
  repeat the full warning, but does not consider this ADR's job done
  until the owner has actually backed both the keystore file and its
  password up somewhere durable and independent of this machine.
- ~~Publishing entity (individual vs. company) — still undecided~~ —
  **decided 2026-09-03: Company/Organization Google Play Console
  account** (owner decision, "FINAL ANSWERS FOR QUESTIONS 11–15", item
  15). Does not require regenerating this keystore — the certificate's
  Distinguished Name (`O=VISTAAR`, deliberately generic) is unrelated
  to the Play Console account's own legal-entity verification; nothing
  here needs to change once a real registered business name exists.
  See `docs/17-legal/app-store-submission-checklist.md` §1 for the
  concrete next step this decision unlocks (a Google-required D-U-N-S
  number for organization accounts — confirmed directly against
  Google's current Play Console documentation, a real requirement this
  ADR did not previously know to flag).
- No Google Play Console account exists yet — this ADR prepares
  signing, it does not create an account or upload anything.
