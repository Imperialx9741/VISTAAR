import 'package:flutter_contacts/flutter_contacts.dart';

/// Book for Someone Else's native Contacts picker (owner-approved
/// 2026-09-01; scoped, but deferred, in
/// `mobile-app-implementation-plan.md` §6.2 since 2026-08-29).
///
/// Deliberately built around [FlutterContacts.native.showPicker] — the
/// OS's own native contact-picker UI — rather than fetching this app's
/// own in-app list via [FlutterContacts.getAll]. That choice is what
/// makes "read only the selected contact's name and phone number" (§6.2's
/// own scope line) literally true: this class never asks the device for
/// more than one contact's data at a time, so there is no bulk contact
/// list ever held in memory to accidentally log, cache, or upload — the
/// native picker mediates browsing/searching entirely inside the OS's
/// own Contacts app UI, outside this app's process.
///
/// Every actual `flutter_contacts` call is behind an injected closure
/// (optional, defaulting to the real static calls) — the same
/// "constructor-injected dependency, real implementation by default"
/// shape `PushNotificationManager` already established for exactly the
/// same reason: `flutter_contacts` needs a native platform channel no
/// widget/unit test here can provide, so tests substitute plain fakes.
class ContactsApi {
  ContactsApi({
    Future<PermissionStatus> Function()? requestPermission,
    Future<Contact?> Function()? showPicker,
  }) : _requestPermission =
           requestPermission ??
           (() => FlutterContacts.permissions.request(PermissionType.read)),
       _showPicker =
           showPicker ??
           (() => FlutterContacts.native.showPicker(
             properties: {ContactProperty.phone},
           ));

  final Future<PermissionStatus> Function() _requestPermission;
  final Future<Contact?> Function() _showPicker;

  /// Requests read-only Contacts access. Shows the system permission
  /// dialog only the first time (or if previously denied but not yet
  /// permanently) — repeat calls after a grant/permanent-denial resolve
  /// immediately without a dialog, `flutter_contacts`' own documented
  /// behavior. Returns `true` for [PermissionStatus.granted] or
  /// [PermissionStatus.limited] (iOS 18+'s "selected contacts only"
  /// mode — the native picker below still works fine with it); `false`
  /// for every other status, which the caller must treat as "keep the
  /// manual entry fallback," never as an error to surface loudly.
  Future<bool> requestPermission() async {
    final status = await _requestPermission();
    return status == PermissionStatus.granted ||
        status == PermissionStatus.limited;
  }

  /// Opens the native contact picker restricted to just the phone-number
  /// property (name is always included by the platform regardless).
  /// Must only be called after [requestPermission] has returned `true`
  /// — Android's picker throws a `PlatformException` when asked for a
  /// non-empty property set without `READ_CONTACTS` granted (iOS's own
  /// picker doesn't need it, but this class calls both from the same
  /// gated path for one consistent, testable flow on both platforms).
  ///
  /// Returns `null` — never throws — if the user cancelled the picker,
  /// or if the contact they picked has no name or no phone number to
  /// prefill the booking form with; the caller's existing manual entry
  /// fields are the fallback in every one of those cases, same as a
  /// denied permission.
  Future<PickedContact?> pickContact() async {
    final contact = await _showPicker();
    if (contact == null) return null;
    final name = contact.displayName?.trim() ?? '';
    if (name.isEmpty || contact.phones.isEmpty) return null;
    return PickedContact(name: name, phone: contact.phones.first.number);
  }
}

/// Just the two fields Book for Someone Else's form actually has —
/// deliberately not the full `flutter_contacts` [Contact] model, so
/// nothing else read off the picked contact (email, address, photo,
/// notes...) can ever leak into a call site by accident.
class PickedContact {
  const PickedContact({required this.name, required this.phone});

  final String name;
  final String phone;
}
