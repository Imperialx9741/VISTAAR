import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../features/auth/app_role.dart';
import '../api/auth_api.dart';
import 'token_storage.dart';

/// Real [TokenStorage] backed by the platform keychain (iOS/macOS) /
/// keystore (Android) / equivalent (web: browser storage — `flutter_
/// secure_storage` does not encrypt on web, a known platform limitation,
/// acceptable for this first slice since web is not the primary target).
class SecureTokenStorage implements TokenStorage {
  SecureTokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _roleKey = 'vistaar.session.role';
  static const _accessTokenKey = 'vistaar.session.access_token';
  static const _refreshTokenKey = 'vistaar.session.refresh_token';
  static const _expiresAtKey = 'vistaar.session.expires_at';

  @override
  Future<void> save(StoredSession session) async {
    await Future.wait([
      _storage.write(key: _roleKey, value: session.role.accountType),
      _storage.write(
        key: _accessTokenKey,
        value: session.tokens.accessToken,
      ),
      _storage.write(
        key: _refreshTokenKey,
        value: session.tokens.refreshToken,
      ),
      _storage.write(
        key: _expiresAtKey,
        value: session.expiresAt.toIso8601String(),
      ),
    ]);
  }

  @override
  Future<StoredSession?> load() async {
    final values = await Future.wait([
      _storage.read(key: _roleKey),
      _storage.read(key: _accessTokenKey),
      _storage.read(key: _refreshTokenKey),
      _storage.read(key: _expiresAtKey),
    ]);
    final [roleValue, accessToken, refreshToken, expiresAtValue] = values;
    if (roleValue == null ||
        accessToken == null ||
        refreshToken == null ||
        expiresAtValue == null) {
      return null;
    }

    AppRole? role;
    for (final candidate in AppRole.values) {
      if (candidate.accountType == roleValue) {
        role = candidate;
        break;
      }
    }
    final expiresAt = DateTime.tryParse(expiresAtValue);
    if (role == null || expiresAt == null) {
      // Corrupt/unrecognized stored value — safer to treat as no session
      // than to crash the app on startup.
      await clear();
      return null;
    }

    return StoredSession(
      role: role,
      tokens: AuthTokens(
        accessToken: accessToken,
        refreshToken: refreshToken,
        expiresInSeconds:
            expiresAt.difference(DateTime.now()).inSeconds.clamp(0, 1 << 31),
      ),
      expiresAt: expiresAt,
    );
  }

  @override
  Future<void> clear() async {
    await Future.wait([
      _storage.delete(key: _roleKey),
      _storage.delete(key: _accessTokenKey),
      _storage.delete(key: _refreshTokenKey),
      _storage.delete(key: _expiresAtKey),
    ]);
  }
}
