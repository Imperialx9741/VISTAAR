import '../../features/auth/app_role.dart';
import '../api/auth_api.dart';

/// What gets persisted across app restarts. Separate from [AuthTokens]
/// (which mirrors the raw `POST /api/v1/auth/otp/verify` response,
/// api-contracts.md §7) because storage also needs an absolute
/// [expiresAt] — the API only gives a relative `expires_in` seconds
/// count, useful only at the moment it was received.
class StoredSession {
  StoredSession({
    required this.role,
    required this.tokens,
    required this.expiresAt,
  });

  final AppRole role;
  final AuthTokens tokens;
  final DateTime expiresAt;

  bool get isExpired => DateTime.now().isAfter(expiresAt);
}

/// Persists (and clears) the current login session so it survives an app
/// restart. An interface, not a concrete class, so tests can inject an
/// in-memory fake instead of touching the real platform keychain/keystore
/// — the same fake-implementation-of-a-Protocol pattern the backend uses
/// throughout (e.g. modules/*/ports.py + tests/test_*_service.py).
abstract class TokenStorage {
  Future<void> save(StoredSession session);
  Future<StoredSession?> load();
  Future<void> clear();
}
