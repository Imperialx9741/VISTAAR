/// The two login options this app presents, per ADR-0027. Maps directly
/// to the backend's `identity.accounts.account_type` — `AccountType.
/// CUSTOMER`/`AccountType.DRIVER` — this app never authenticates as
/// `ADMIN` (Admin Web is a separate application).
///
/// User-facing labels ("User" / "Sarthi") are an owner decision,
/// 2026-08-29 — display text only, the wire `accountType` values below
/// are unchanged (still exactly what the backend's OTP endpoints expect,
/// api-contracts.md §6.1).
enum AppRole {
  user('CUSTOMER', 'User'),
  sarthi('DRIVER', 'Sarthi');

  const AppRole(this.accountType, this.displayName);

  /// The exact string this app sends as `account_type` in
  /// `POST /api/v1/auth/otp/request` (api-contracts.md §6.1).
  final String accountType;

  /// What the login screen shows the user for this role.
  final String displayName;
}
