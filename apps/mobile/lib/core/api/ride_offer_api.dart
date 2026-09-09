import 'api_client.dart';
import 'api_exception.dart';

/// A pickup location's coordinates, as embedded in a ride offer
/// (api-contracts.md §16.1). `null` on the wire means the ride no longer
/// exists by the time offers were listed — the offer itself is still
/// returned (already-expired/responded offers stay visible briefly) but
/// with no pickup to show.
class OfferPickup {
  const OfferPickup({required this.latitude, required this.longitude});

  final double latitude;
  final double longitude;
}

/// One row of `GET /api/v1/drivers/me/ride-offers` (api-contracts.md
/// §16.1) — a ride dispatched to this driver, awaiting Accept/Reject
/// before [expiresAt].
class RideOffer {
  const RideOffer({
    required this.offerId,
    required this.rideId,
    required this.status,
    required this.expiresAt,
    required this.pickup,
  });

  factory RideOffer.fromJson(Map<String, dynamic> json) {
    final pickupJson = json['pickup'] as Map<String, dynamic>?;
    return RideOffer(
      offerId: json['offer_id'] as String,
      rideId: json['ride_id'] as String,
      status: json['status'] as String,
      expiresAt: DateTime.parse(json['expires_at'] as String),
      pickup: pickupJson == null
          ? null
          : OfferPickup(
              latitude: (pickupJson['latitude'] as num).toDouble(),
              longitude: (pickupJson['longitude'] as num).toDouble(),
            ),
    );
  }

  final String offerId;
  final String rideId;

  /// Wire values from `OfferStatus` — `"PENDING"` is the only one a
  /// driver should ever act on; the others (`EXPIRED`, `ACCEPTED`,
  /// `REJECTED`) only show up in the brief window before the backend's
  /// lazy-expiry sweep removes them from this list.
  final String status;
  final DateTime expiresAt;
  final OfferPickup? pickup;

  bool get isPending => status == 'PENDING';

  Duration remaining({DateTime? now}) =>
      expiresAt.difference(now ?? DateTime.now().toUtc());
}

/// Result of a successful `POST .../{offer_id}/accept`
/// (api-contracts.md §16.3) — `rideStatus` is the *ride's* new status
/// (`"ACCEPTED"`), not the offer's, matching the backend's own response
/// shape.
class AcceptOfferResult {
  const AcceptOfferResult({
    required this.offerId,
    required this.rideId,
    required this.rideStatus,
    required this.walletBalance,
  });

  final String offerId;
  final String rideId;
  final String rideStatus;
  final double walletBalance;
}

/// Calls the Sarthi (driver) ride-offer endpoints (api-contracts.md
/// §16) — list, accept, reject. Mirrors [DriverAvailabilityApi]'s
/// token-handling: the access token is read fresh from `AuthSession` on
/// every call, never captured at construction time.
class RideOfferApi {
  RideOfferApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  Future<List<RideOffer>> listOffers() async {
    final data = await _client.get(
      '/api/v1/drivers/me/ride-offers',
      accessToken: _requireToken(),
    );
    final offers = (data['offers'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return offers.map(RideOffer.fromJson).toList(growable: false);
  }

  /// [idempotencyKey] must be generated once per accept *attempt* by the
  /// caller and reused across retries of that same attempt (a fresh UUID
  /// per distinct attempt) — this method does not generate one itself,
  /// so a retried call after a network error replays idempotently
  /// instead of risking two accepts for one tap.
  Future<AcceptOfferResult> acceptOffer(
    String offerId, {
    required String idempotencyKey,
  }) async {
    final data = await _client.post(
      '/api/v1/drivers/me/ride-offers/$offerId/accept',
      body: const {},
      accessToken: _requireToken(),
      extraHeaders: {'Idempotency-Key': idempotencyKey},
    );
    return AcceptOfferResult(
      offerId: data['offer_id'] as String,
      rideId: data['ride_id'] as String,
      rideStatus: data['status'] as String,
      walletBalance: (data['wallet_balance'] as num).toDouble(),
    );
  }

  Future<void> rejectOffer(String offerId) async {
    await _client.post(
      '/api/v1/drivers/me/ride-offers/$offerId/reject',
      body: const {},
      accessToken: _requireToken(),
    );
  }
}
