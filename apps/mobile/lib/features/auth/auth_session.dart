import 'dart:async' show unawaited;

import 'package:flutter/foundation.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_exception.dart';
import '../../core/api/auth_api.dart';
import '../../core/storage/token_storage.dart';
import 'app_role.dart';

/// Holds the current login session in memory and notifies listeners
/// (the app's root widget) when it changes, so the app can switch between
/// the login flow and the role-appropriate home screen.
///
/// Persists across app restarts via [TokenStorage] — [signIn] writes,
/// [signOut] clears, and [restore] (called once, at startup) reads back
/// whatever was last saved. Persistence itself is fire-and-forget from
/// the caller's perspective: [signIn]/[signOut] update in-memory state
/// and notify listeners synchronously, so the UI never waits on disk/
/// keychain I/O to react.
///
/// Real token refresh (ADR-0076, 2026-09-07): wires itself onto
/// [apiClient]'s `onAuthInvalid` at construction, so any API call
/// anywhere in the app that hits an expired access token transparently
/// refreshes and retries — the caller never sees the failure. See
/// [_refreshTokens]'s own doc comment for the single-flight/rotation
/// details that make this safe under concurrent calls.
class AuthSession extends ChangeNotifier {
  // Public constructor parameters deliberately don't spell the private
  // field names (same reasoning as the original `storage`/`_storage`
  // split already established here) — call sites shouldn't have to
  // know this class's own internal field naming.
  AuthSession({
    required TokenStorage storage,
    required AuthApi authApi,
    required ApiClient apiClient,
    // ignore: prefer_initializing_formals
  }) : _storage = storage,
       // ignore: prefer_initializing_formals
       _authApi = authApi {
    apiClient.onAuthInvalid = _refreshTokens;
  }

  final TokenStorage _storage;
  final AuthApi _authApi;

  AppRole? _role;
  AuthTokens? _tokens;

  /// Non-null while a refresh is in flight — concurrent callers
  /// (several screens' API calls all hitting AUTH_INVALID around the
  /// same moment) share this one real `/refresh` call and its result,
  /// rather than each racing to spend the same single-use refresh
  /// token (server-side rotation means only the first would succeed).
  Future<String?>? _refreshInFlight;

  AppRole? get role => _role;
  AuthTokens? get tokens => _tokens;
  bool get isAuthenticated => _tokens != null;

  void signIn({required AppRole role, required AuthTokens tokens}) {
    _role = role;
    _tokens = tokens;
    notifyListeners();
    unawaited(
      _storage.save(
        StoredSession(
          role: role,
          tokens: tokens,
          expiresAt: DateTime.now().add(
            Duration(seconds: tokens.expiresInSeconds),
          ),
        ),
      ),
    );
  }

  void signOut() {
    _role = null;
    _tokens = null;
    notifyListeners();
    unawaited(_storage.clear());
  }

  /// Reads back a previously-saved session, if one exists. A session
  /// whose *access* token has expired now attempts one real refresh
  /// (ADR-0076) before giving up — the refresh token that same session
  /// carries typically outlives the access token by a wide margin, so
  /// this is the common case on a cold start well after the access
  /// token's own short lifetime, not an edge case. Only a session whose
  /// refresh token is *itself* invalid/expired/revoked (or whose
  /// account is now suspended) actually ends in a cleared session,
  /// same as before this ADR.
  Future<void> restore() async {
    final stored = await _storage.load();
    if (stored == null) return;
    if (!stored.isExpired) {
      _role = stored.role;
      _tokens = stored.tokens;
      notifyListeners();
      return;
    }

    _role = stored.role;
    _tokens = stored.tokens;
    final refreshed = await _refreshTokens();
    if (refreshed == null) {
      // _refreshTokens() already called signOut() (clears storage) on
      // failure — nothing further to do here.
      return;
    }
    // signIn() (called inside _refreshTokens() via the successful path)
    // already set _role/_tokens and notified — nothing further needed.
  }

  /// One refresh attempt, single-flight (see [_refreshInFlight]'s own
  /// doc comment). Returns the new access token on success (also
  /// updates [tokens]/persists via [signIn], exactly as a fresh login
  /// would); returns `null` and signs out for real on failure — the
  /// refresh token itself is no longer usable, so there is no session
  /// left to keep. Wired directly onto `ApiClient.onAuthInvalid`.
  Future<String?> _refreshTokens() {
    return _refreshInFlight ??= _doRefresh().whenComplete(() {
      _refreshInFlight = null;
    });
  }

  Future<String?> _doRefresh() async {
    final role = _role;
    final currentRefreshToken = _tokens?.refreshToken;
    if (role == null || currentRefreshToken == null) return null;
    try {
      final newTokens = await _authApi.refresh(currentRefreshToken);
      signIn(role: role, tokens: newTokens);
      return newTokens.accessToken;
    } on ApiException {
      signOut();
      return null;
    }
  }
}
