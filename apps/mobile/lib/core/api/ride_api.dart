import 'api_client.dart';
import 'api_exception.dart';
import 'upload_target.dart';

/// A latitude/longitude pair — this app's own value type for ride
/// creation, distinct from `ride_offer_api.dart`'s `OfferPickup` (that
/// one is response-only and driver-side; this one is also sent in a
/// request body).
class RideGeoPoint {
  const RideGeoPoint({required this.latitude, required this.longitude});

  final double latitude;
  final double longitude;

  Map<String, double> toJson() => {
    'latitude': latitude,
    'longitude': longitude,
  };

  static RideGeoPoint fromJson(Map<String, dynamic> json) => RideGeoPoint(
    latitude: (json['latitude'] as num).toDouble(),
    longitude: (json['longitude'] as num).toDouble(),
  );
}

/// `fare` as returned by both Create Ride (§12) and Get Ride (§13) —
/// `null` until a fare quote exists, which in practice is never (Create
/// Ride always computes one synchronously before responding).
class RideFare {
  const RideFare({
    required this.base,
    required this.discount,
    required this.total,
    required this.currency,
  });

  factory RideFare.fromJson(Map<String, dynamic> json) => RideFare(
    base: (json['base'] as num).toDouble(),
    discount: (json['discount'] as num).toDouble(),
    total: (json['total'] as num).toDouble(),
    currency: json['currency'] as String,
  );

  final double base;
  final double discount;
  final double total;
  final String currency;
}

/// Outstanding Customer Penalty Display (ADR-0026, IMPLEMENTED
/// 2026-09-02) — `null` when the customer has no OUTSTANDING
/// `penalty.penalties` row (the common case).
class OutstandingPenalty {
  const OutstandingPenalty({required this.amount, required this.currency});

  factory OutstandingPenalty.fromJson(Map<String, dynamic> json) =>
      OutstandingPenalty(
        amount: (json['amount'] as num).toDouble(),
        currency: json['currency'] as String,
      );

  final double amount;
  final String currency;
}

/// `outstanding_penalty` broken back down alongside the ride fare, so
/// this app never has to re-derive the combined figure itself (BR-002's
/// transparency requirement). Informational only — `total` is never
/// collected as one transaction (ADR-0026): `rideFare` is still paid
/// P2P, directly to the Sarthi (ADR-0025); only `outstandingPenalty`,
/// if non-zero, is ever owed to VISTAAR, through a collection mechanism
/// that doesn't exist yet (ADR-0026 §5, still undecided) — this app
/// only ever shows the number, never offers to collect it.
class TotalPayable {
  const TotalPayable({
    required this.rideFare,
    required this.outstandingPenalty,
    required this.total,
    required this.currency,
  });

  factory TotalPayable.fromJson(Map<String, dynamic> json) => TotalPayable(
    rideFare: (json['ride_fare'] as num).toDouble(),
    outstandingPenalty: (json['outstanding_penalty'] as num).toDouble(),
    total: (json['total'] as num).toDouble(),
    currency: json['currency'] as String,
  );

  final double rideFare;
  final double outstandingPenalty;
  final double total;
  final String currency;
}

/// Result of `POST /api/v1/rides` (api-contracts.md §12).
class RideCreationResult {
  const RideCreationResult({
    required this.rideId,
    required this.status,
    required this.fare,
    required this.outstandingPenalty,
    required this.totalPayable,
  });

  factory RideCreationResult.fromJson(Map<String, dynamic> json) {
    final fareJson = json['fare'] as Map<String, dynamic>?;
    final outstandingPenaltyJson =
        json['outstanding_penalty'] as Map<String, dynamic>?;
    final totalPayableJson = json['total_payable'] as Map<String, dynamic>?;
    return RideCreationResult(
      rideId: json['ride_id'] as String,
      status: json['status'] as String,
      fare: fareJson == null ? null : RideFare.fromJson(fareJson),
      outstandingPenalty: outstandingPenaltyJson == null
          ? null
          : OutstandingPenalty.fromJson(outstandingPenaltyJson),
      totalPayable: totalPayableJson == null
          ? null
          : TotalPayable.fromJson(totalPayableJson),
    );
  }

  final String rideId;
  final String status;
  final RideFare? fare;
  final OutstandingPenalty? outstandingPenalty;
  final TotalPayable? totalPayable;
}

/// ADR-0057 (Book for Someone Else) — sent on `POST /api/v1/rides` when
/// the booker names someone else as the actual rider. Picked by the
/// booker typing the name/phone by hand — this app doesn't integrate a
/// native Contacts picker (a real, separately-scoped native-permission
/// feature; `mobile-app-implementation-plan.md` §6.2's own "if denied,
/// type it by hand" fallback is this app's *primary* path for now, not
/// just a fallback).
class LinkedContact {
  const LinkedContact({required this.name, required this.phone});

  final String name;
  final String phone;

  Map<String, String> toJson() => {'name': name, 'phone': phone};
}

/// One row of `GET /api/v1/rides` (api-contracts.md §12.1, ADR-0057) —
/// deliberately lighter than [RideStatusDetail] (no driver/vehicle/fare)
/// per that endpoint's own doc comment.
class RideListItem {
  const RideListItem({
    required this.rideId,
    required this.status,
    required this.scheduledFor,
    required this.pickup,
    required this.destination,
  });

  factory RideListItem.fromJson(Map<String, dynamic> json) => RideListItem(
    rideId: json['ride_id'] as String,
    status: json['status'] as String,
    scheduledFor: json['scheduled_for'] == null
        ? null
        : DateTime.parse(json['scheduled_for'] as String),
    pickup: RideGeoPoint.fromJson(json['pickup'] as Map<String, dynamic>),
    destination: RideGeoPoint.fromJson(
      json['destination'] as Map<String, dynamic>,
    ),
  );

  final String rideId;
  final String status;
  final DateTime? scheduledFor;
  final RideGeoPoint pickup;
  final RideGeoPoint destination;
}

/// One page of `GET /api/v1/rides` (§50's shared pagination shape).
class RideListPage {
  const RideListPage({
    required this.items,
    required this.page,
    required this.totalPages,
  });

  final List<RideListItem> items;
  final int page;
  final int totalPages;

  bool get hasMore => page < totalPages;
}

class RideDriverInfo {
  const RideDriverInfo({
    required this.driverId,
    required this.fullName,
    required this.profilePhotoUri,
  });

  factory RideDriverInfo.fromJson(Map<String, dynamic> json) => RideDriverInfo(
    driverId: json['driver_id'] as String,
    fullName: json['full_name'] as String,
    profilePhotoUri: json['profile_photo_uri'] as String?,
  );

  final String driverId;
  final String fullName;
  final String? profilePhotoUri;
}

class RideVehicleInfo {
  const RideVehicleInfo({
    required this.vehicleId,
    required this.category,
    required this.registrationNumber,
    required this.make,
    required this.model,
  });

  factory RideVehicleInfo.fromJson(Map<String, dynamic> json) =>
      RideVehicleInfo(
        vehicleId: json['vehicle_id'] as String,
        category: json['category'] as String,
        registrationNumber: json['registration_number'] as String,
        make: json['make'] as String,
        model: json['model'] as String,
      );

  final String vehicleId;
  final String category;
  final String registrationNumber;
  final String make;
  final String model;
}

/// `GET /api/v1/rides/{ride_id}` (api-contracts.md §13). `payment` is
/// always `null` on the wire (no Payment domain exists) — not modeled
/// here since nothing in this app reads it yet.
class RideStatusDetail {
  const RideStatusDetail({
    required this.rideId,
    required this.status,
    required this.scheduledFor,
    required this.pickup,
    required this.destination,
    required this.driver,
    required this.vehicle,
    required this.fare,
  });

  factory RideStatusDetail.fromJson(Map<String, dynamic> json) {
    final driverJson = json['driver'] as Map<String, dynamic>?;
    final vehicleJson = json['vehicle'] as Map<String, dynamic>?;
    final fareJson = json['fare'] as Map<String, dynamic>?;
    return RideStatusDetail(
      rideId: json['ride_id'] as String,
      status: json['status'] as String,
      scheduledFor: json['scheduled_for'] == null
          ? null
          : DateTime.parse(json['scheduled_for'] as String),
      pickup: RideGeoPoint.fromJson(json['pickup'] as Map<String, dynamic>),
      destination: RideGeoPoint.fromJson(
        json['destination'] as Map<String, dynamic>,
      ),
      driver: driverJson == null ? null : RideDriverInfo.fromJson(driverJson),
      vehicle: vehicleJson == null
          ? null
          : RideVehicleInfo.fromJson(vehicleJson),
      fare: fareJson == null ? null : RideFare.fromJson(fareJson),
    );
  }

  final String rideId;

  /// One of `RideStatus`'s wire values: SEARCHING, ACCEPTED, ARRIVED,
  /// STARTED, COMPLETED, CANCELLED, CLOSED (backend
  /// `modules/ride/domain/entities.py`). There is no `NO_DRIVER` value —
  /// state-machines.md never defines one, so a ride that finds no driver
  /// simply stays SEARCHING; api-contracts.md §21's documented
  /// retry/increase-fare endpoints do not exist anywhere in the live
  /// backend (verified — no route for them in `modules/ride/router.py`
  /// or elsewhere), so this app cannot build against them yet. There is
  /// also `SCHEDULED` (ADR-0057) — entered instead of `SEARCHING` when
  /// [scheduledFor] was given at booking; a Celery Beat task promotes
  /// it to `SEARCHING` once its 30-minute lock-in window arrives.
  final String status;

  /// Non-null only while [status] is `SCHEDULED` (ADR-0057) — when the
  /// ride is actually meant to happen.
  final DateTime? scheduledFor;
  final RideGeoPoint pickup;
  final RideGeoPoint destination;
  final RideDriverInfo? driver;
  final RideVehicleInfo? vehicle;
  final RideFare? fare;

  static const _terminalStatuses = {'COMPLETED', 'CANCELLED', 'CLOSED'};

  bool get isTerminal => _terminalStatuses.contains(status);
}

/// Calls the ride-lifecycle endpoints actually implemented by the live
/// backend (api-contracts.md §12, §13, §17, §18, §28) — both User
/// (create/get/OTP-reveal) and Sarthi (arrive/start/complete) sides.
/// [getRide] is genuinely shared: `GET /api/v1/rides/{ride_id}` is
/// ownership-checked for *either* the ride's customer or its assigned
/// driver (`require_customer_or_driver`), so one method serves both
/// roles' status-polling screens. Mirrors [DriverAvailabilityApi]/
/// [RideOfferApi]'s token-handling: the access token is read fresh from
/// `AuthSession` on every call.
class RideApi {
  RideApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  /// [idempotencyKey] must be generated by the caller — a fresh one per
  /// submit tap is fine here (unlike accept-offer, this is a one-shot
  /// user-initiated form submission with no automatic retry logic in
  /// this app; the caller's own "disable the button while busy" already
  /// prevents a double-tap from firing two creates).
  /// [scheduledFor] (ADR-0057, Schedule a Ride) makes this a scheduled
  /// booking instead of an immediate one — the backend enforces the
  /// 1-24 hour window (BR-137), not this app. [linkedContact] (ADR-0057,
  /// Book for Someone Else) names who's actually riding, if not the
  /// booker themselves. Both are independent and optional.
  ///
  /// No payment-method field is sent (owner decision, 2026-09-03): the
  /// User settles the fare directly with the Sarthi by whatever means
  /// they agree — VISTAAR never asks the User to pick UPI/Cash/etc. See
  /// modules/ride/domain/entities.py's own docstring on the backend for
  /// the full account of why the field existed and was removed.
  Future<RideCreationResult> createRide({
    required RideGeoPoint pickup,
    required RideGeoPoint destination,
    required String vehicleCategory,
    String? cabTier,
    required String idempotencyKey,
    DateTime? scheduledFor,
    LinkedContact? linkedContact,
  }) async {
    final data = await _client.post(
      '/api/v1/rides',
      body: {
        'pickup': pickup.toJson(),
        'destination': destination.toJson(),
        'vehicle_category': vehicleCategory,
        'cab_tier': ?cabTier,
        'scheduled_for': ?scheduledFor?.toUtc().toIso8601String(),
        'linked_contact': ?linkedContact?.toJson(),
      },
      accessToken: _requireToken(),
      extraHeaders: {'Idempotency-Key': idempotencyKey},
    );
    return RideCreationResult.fromJson(data);
  }

  /// List My Rides (api-contracts.md §12.1, ADR-0057) — added so a
  /// customer can browse their own upcoming scheduled rides across
  /// sessions, not just the one they just booked. [status] filters
  /// server-side (e.g. `'SCHEDULED'`); omitted, every status is
  /// returned.
  Future<RideListPage> listMyRides({String? status, int page = 1}) async {
    final query = StringBuffer('page=$page');
    if (status != null) query.write('&status=$status');
    final data = await _client.get(
      '/api/v1/rides?$query',
      accessToken: _requireToken(),
    );
    final items = (data['items'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(RideListItem.fromJson)
        .toList(growable: false);
    final pagination = data['pagination'] as Map<String, dynamic>;
    return RideListPage(
      items: items,
      page: pagination['page'] as int,
      totalPages: pagination['total_pages'] as int,
    );
  }

  Future<RideStatusDetail> getRide(String rideId) async {
    final data = await _client.get(
      '/api/v1/rides/$rideId',
      accessToken: _requireToken(),
    );
    return RideStatusDetail.fromJson(data);
  }

  /// Only ever succeeds while the ride is ARRIVED (`RideService.
  /// refresh_otp()`'s own gate) — SEARCHING/ACCEPTED/STARTED all raise a
  /// domain error the caller sees as an [ApiException]. Each call
  /// invalidates the previous code and issues a new one; there is no
  /// separate "peek without refreshing" endpoint.
  Future<String> refreshOtp(String rideId) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/otp/refresh',
      body: const {},
      accessToken: _requireToken(),
    );
    return data['otp'] as String;
  }

  /// Driver Arrival (api-contracts.md §17). GPS-gated server-side
  /// against the pickup radius — `NOT_WITHIN_PICKUP_RADIUS` is
  /// retriable (the caller may call this again with a fresh position);
  /// `GPS_VERIFICATION_FAILED` (after `RIDE_GPS_MAX_ATTEMPTS_BEFORE_
  /// REVIEW` failures) is terminal, pending manual review — the thrown
  /// [ApiException.details] carries `{"dispute_id": "..."}`
  /// (ADR-0032/ADR-0074), which [RideExecutionScreen] catches and opens
  /// [GpsDisputeScreen] with. Returns the new status (`"ARRIVED"`).
  Future<String> markArrived(
    String rideId, {
    required double latitude,
    required double longitude,
  }) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/arrived',
      body: {'latitude': latitude, 'longitude': longitude},
      accessToken: _requireToken(),
    );
    return data['status'] as String;
  }

  /// Start Ride (api-contracts.md §18) — the driver enters the code the
  /// customer reads aloud (never seen by the driver's own app; only
  /// `RideApi.refreshOtp()`, customer-only, ever returns the plaintext).
  /// A wrong code increments the OTP's attempt counter server-side
  /// (`OTP_INVALID`); exceeding it is terminal for that OTP
  /// (`OTP_MAX_ATTEMPTS`) — the customer must reveal a fresh one.
  /// Returns the new status (`"STARTED"`).
  Future<String> startRide(String rideId, {required String otp}) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/start',
      body: {'otp': otp},
      accessToken: _requireToken(),
    );
    return data['status'] as String;
  }

  /// Ride Completion (api-contracts.md §28). GPS-gated against the
  /// destination radius, same retriable/terminal error split as
  /// [markArrived] — including the same `dispute_id`-carrying terminal
  /// failure. A success transitions STARTED straight through COMPLETED
  /// to CLOSED server-side in one step (ADR-0028 Decision 3) — the
  /// returned status is `"CLOSED"`, not `"COMPLETED"`.
  Future<String> completeRide(
    String rideId, {
    required double latitude,
    required double longitude,
  }) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/complete',
      body: {'latitude': latitude, 'longitude': longitude},
      accessToken: _requireToken(),
    );
    return data['status'] as String;
  }

  /// Customer Cancellation (api-contracts.md §19). Allowed from
  /// SEARCHING, ACCEPTED, or ARRIVED — [reason] is free text (the
  /// backend enforces no canonical reason enum, just non-blank/≤100
  /// chars). [CancelRideResult.charge] is `null` only for a SEARCHING
  /// cancellation (nothing chargeable yet); always populated for a
  /// post-acceptance one, even when the amount is ₹0 (grace period or
  /// first qualifying cancellation).
  Future<CancelRideResult> cancelRide(
    String rideId, {
    required String reason,
  }) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/cancel',
      body: {'reason': reason},
      accessToken: _requireToken(),
    );
    return CancelRideResult.fromJson(data);
  }

  /// Driver Cancellation (api-contracts.md §20). Allowed from ACCEPTED
  /// only — state-machines.md §13 deliberately excludes ARRIVED,
  /// unlike the customer side (confirmed by reading
  /// `RideService.driver_cancel_ride()` directly, not just the plan's
  /// own earlier wording). [reason] is free text, same validation as
  /// [cancelRide] — this method does not expose
  /// `"CHANGED_PICKUP_OVER_250M"` as a selectable option; that old
  /// ₹0-penalty/no-strike exemption belonged to the pickup-change
  /// driver-decision flow, which no longer exists (ADR-0056) — it isn't
  /// reachable from this screen either way. Returns the new status
  /// (`"CANCELLED"`).
  Future<String> driverCancelRide(
    String rideId, {
    required String reason,
  }) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/driver-cancel',
      body: {'reason': reason},
      accessToken: _requireToken(),
    );
    return data['ride_status'] as String;
  }

  /// Pickup Change (api-contracts.md §22, ADR-0056 — owner decision,
  /// 2026-08-31). Customer-only, ACCEPTED-only
  /// (`RideService.request_pickup_change()`'s own gate — pickup change
  /// only makes sense before the driver has arrived). A ≤100m change
  /// applies immediately (`applied: true`); a >100m change throws an
  /// [ApiException] with code `PICKUP_CHANGE_TOO_FAR` — there is no
  /// driver decision or charge of any kind anymore (the old >250m
  /// PROCEED/PASS flow, ADR-0033, was removed). The backend's own
  /// message already tells the customer to cancel and rebook instead;
  /// this method doesn't add a second one.
  Future<PickupChangeResult> changePickup(
    String rideId, {
    required double latitude,
    required double longitude,
  }) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/pickup-change',
      body: {'latitude': latitude, 'longitude': longitude},
      accessToken: _requireToken(),
    );
    return PickupChangeResult(
      applied: data['applied'] as bool,
      distanceMeters: (data['distance_meters'] as num).toDouble(),
    );
  }

  /// Destination Change (api-contracts.md §25, ADR-0033 Decision 9;
  /// unaffected by ADR-0056). Customer-only, STARTED-only
  /// (`RideService.get_ride_for_destination_change()`'s own gate —
  /// destination change happens mid-ride, after pickup, unlike pickup
  /// change). A WITHIN_ROUTE change applies immediately (`applied:
  /// true`, no charge, BR-079). A BEYOND_ORIGINAL/DIFFERENT_ROUTE
  /// change instead creates a pending request (`applied: false`) —
  /// **verified against the live router that this response never
  /// includes the computed fare**, only [confirmDestinationChange]'s
  /// response does, once already confirmed. That makes it impossible
  /// to show the customer the revised fare *before* they decide,
  /// exactly what BR-082 ("Customer sees revised fare → Customer
  /// confirms") requires — a real, verified backend gap, not assumed.
  /// This app does not build a "confirm blind" screen around it; see
  /// [confirmDestinationChange]'s own doc comment for how the pending
  /// request this creates gets cleaned up instead.
  Future<DestinationChangeResult> changeDestination(
    String rideId, {
    required double latitude,
    required double longitude,
  }) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/destination-change',
      body: {'latitude': latitude, 'longitude': longitude},
      accessToken: _requireToken(),
    );
    return DestinationChangeResult(
      applied: data['applied'] as bool,
      caseType: data['case'] as String,
      changeRequestId: data['change_request_id'] as String?,
    );
  }

  /// Destination Change Confirmation (api-contracts.md §26). This app
  /// only ever calls this with `confirmed: false` — to reject a
  /// BEYOND_ORIGINAL/DIFFERENT_ROUTE request [changeDestination] just
  /// created, immediately after showing the customer that this app
  /// can't yet display the fare a "yes" would commit them to (see that
  /// method's own doc comment). Rejecting, rather than leaving the
  /// request dangling, matters because the backend allows only one
  /// pending DESTINATION_CHANGE request per ride at a time
  /// (`DestinationChangeAlreadyRequestedError`) — without this cleanup
  /// call, the customer would be stuck unable to try any destination
  /// change again, including a free WITHIN_ROUTE one, until this one
  /// somehow resolved. `confirmed: true` is never used from this app —
  /// doing so would mean applying a fare change nobody saw first.
  Future<void> rejectDestinationChange(
    String rideId, {
    required String changeRequestId,
  }) async {
    await _client.post(
      '/api/v1/rides/$rideId/destination-change/confirm',
      body: {'change_request_id': changeRequestId, 'confirmed': false},
      accessToken: _requireToken(),
    );
  }

  /// List GPS Disputes for a Ride (api-contracts.md §77, ADR-0074) — the
  /// discovery endpoint a customer needs (unlike the driver, who
  /// receives `dispute_id` directly in the `GPS_VERIFICATION_FAILED`
  /// error's `details` — see [ApiException.details] — that opened it).
  /// Not paginated; a ride has at most two.
  Future<List<GpsDispute>> listGpsDisputes(String rideId) async {
    final data = await _client.get(
      '/api/v1/rides/$rideId/gps-disputes',
      accessToken: _requireToken(),
    );
    return (data['disputes'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(GpsDispute.fromJson)
        .toList(growable: false);
  }

  Future<GpsDispute> getGpsDispute(String rideId, String disputeId) async {
    final data = await _client.get(
      '/api/v1/rides/$rideId/gps-disputes/$disputeId',
      accessToken: _requireToken(),
    );
    return GpsDispute.fromJson(data);
  }

  /// Request Evidence Upload URL (api-contracts.md §77, ADR-0031/
  /// ADR-0065) — same presigned-POST shape as [DriverApi]'s upload-url
  /// endpoint; the returned `uri` is then supplied as-is to
  /// [submitGpsDisputeEvidence].
  Future<UploadTarget> requestGpsDisputeEvidenceUploadUrl(
    String rideId,
    String disputeId, {
    required String contentType,
  }) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/gps-disputes/$disputeId/evidence/upload-url',
      body: {'content_type': contentType},
      accessToken: _requireToken(),
    );
    return UploadTarget.fromJson(data);
  }

  /// `evidenceType` is one of `PHOTO`/`VIDEO`/`DOCUMENT`/`TEXT`; `uri`
  /// is required for the first three, `text` for `TEXT`.
  Future<GpsDisputeEvidence> submitGpsDisputeEvidence(
    String rideId,
    String disputeId, {
    required String evidenceType,
    String? uri,
    String? text,
  }) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/gps-disputes/$disputeId/evidence',
      body: {'evidence_type': evidenceType, 'uri': ?uri, 'text': ?text},
      accessToken: _requireToken(),
    );
    return GpsDisputeEvidence.fromJson(data);
  }
}

/// One `ride.gps_disputes` row plus its evidence trail (api-contracts.md
/// §77, ADR-0032/ADR-0074).
class GpsDispute {
  const GpsDispute({
    required this.disputeId,
    required this.rideId,
    required this.verificationType,
    required this.openedAt,
    required this.evidenceDeadline,
    required this.status,
    required this.decision,
    required this.decidedReason,
    required this.evidence,
  });

  factory GpsDispute.fromJson(Map<String, dynamic> json) => GpsDispute(
    disputeId: json['dispute_id'] as String,
    rideId: json['ride_id'] as String,
    verificationType: json['verification_type'] as String,
    openedAt: DateTime.parse(json['opened_at'] as String),
    evidenceDeadline: DateTime.parse(json['evidence_deadline'] as String),
    status: json['status'] as String,
    decision: json['decision'] as String?,
    decidedReason: json['decided_reason'] as String?,
    evidence: (json['evidence'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(GpsDisputeEvidence.fromJson)
        .toList(growable: false),
  );

  final String disputeId;
  final String rideId;

  /// `"ARRIVAL"` | `"COMPLETION"`.
  final String verificationType;
  final DateTime openedAt;
  final DateTime evidenceDeadline;

  /// `"OPEN"` | `"RESOLVED"` | `"EXPIRED"`.
  final String status;

  /// `"APPROVE"` | `"REJECT"` | `null` (not yet decided).
  final String? decision;
  final String? decidedReason;
  final List<GpsDisputeEvidence> evidence;

  bool get isOpen => status == 'OPEN';
}

class GpsDisputeEvidence {
  const GpsDisputeEvidence({
    required this.submittedBy,
    required this.evidenceType,
    required this.uri,
    required this.textExplanation,
    required this.submittedAt,
  });

  factory GpsDisputeEvidence.fromJson(Map<String, dynamic> json) =>
      GpsDisputeEvidence(
        submittedBy: json['submitted_by'] as String,
        evidenceType: json['evidence_type'] as String,
        uri: json['uri'] as String?,
        textExplanation: json['text_explanation'] as String?,
        submittedAt: DateTime.parse(json['submitted_at'] as String),
      );

  final String submittedBy;

  /// `"PHOTO"` | `"VIDEO"` | `"DOCUMENT"` | `"TEXT"`.
  final String evidenceType;
  final String? uri;
  final String? textExplanation;
  final DateTime submittedAt;
}


/// Result of `POST /api/v1/rides/{ride_id}/destination-change`.
/// [caseType] is one of `WITHIN_ROUTE`/`BEYOND_ORIGINAL`/
/// `DIFFERENT_ROUTE` (`DestinationChangeCase`, backend
/// `modules/pricing/domain/entities.py`). [changeRequestId] is only
/// present when [applied] is `false`.
class DestinationChangeResult {
  const DestinationChangeResult({
    required this.applied,
    required this.caseType,
    required this.changeRequestId,
  });

  final bool applied;
  final String caseType;
  final String? changeRequestId;
}

/// Result of a successful (≤100m, ADR-0056) pickup change — `applied`
/// is always `true` on success; a >100m change never reaches this type
/// at all, it throws instead (see [RideApi.changePickup]'s own doc
/// comment).
class PickupChangeResult {
  const PickupChangeResult({
    required this.applied,
    required this.distanceMeters,
  });

  final bool applied;
  final double distanceMeters;
}

/// The charge (if any) resulting from a customer cancellation —
/// present whenever the ride had already been ACCEPTED/ARRIVED, `null`
/// for a SEARCHING cancellation (api-contracts.md §19).
class CancellationCharge {
  const CancellationCharge({
    required this.amount,
    required this.currency,
    required this.expiresAt,
    required this.penaltyId,
  });

  factory CancellationCharge.fromJson(Map<String, dynamic> json) =>
      CancellationCharge(
        amount: (json['amount'] as num).toDouble(),
        currency: json['currency'] as String,
        expiresAt: json['expires_at'] == null
            ? null
            : DateTime.parse(json['expires_at'] as String),
        penaltyId: json['penalty_id'] as String?,
      );

  final double amount;
  final String currency;

  /// `null` for a grace-period cancellation (no real `penalty.penalties`
  /// row was created for it — ADR-0015 Decision 1, nothing to expire).
  final DateTime? expiresAt;

  /// `null` unless a real penalty row exists — the customer's own
  /// reference for a future dispute (§44). Present whenever [expiresAt]
  /// is too, in practice.
  final String? penaltyId;
}

class CancelRideResult {
  const CancelRideResult({required this.rideStatus, required this.charge});

  factory CancelRideResult.fromJson(Map<String, dynamic> json) {
    final chargeJson = json['charge'] as Map<String, dynamic>?;
    return CancelRideResult(
      rideStatus: json['ride_status'] as String,
      charge: chargeJson == null
          ? null
          : CancellationCharge.fromJson(chargeJson),
    );
  }

  final String rideStatus;
  final CancellationCharge? charge;
}
