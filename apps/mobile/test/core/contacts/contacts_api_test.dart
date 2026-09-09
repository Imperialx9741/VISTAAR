// Unit tests for ContactsApi (Book for Someone Else's native Contacts
// picker, owner-approved 2026-09-01).
//
// Every actual `flutter_contacts` call is injected (see that class's own
// doc comment) — no real `FlutterContacts` call is ever made here, since
// no widget/unit test in this app can reach the native platform channel
// it needs.

import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vistaar_mobile/core/contacts/contacts_api.dart';

Contact _contact({String? displayName, List<Phone> phones = const []}) =>
    Contact(displayName: displayName, phones: phones);

void main() {
  group('requestPermission', () {
    test('granted resolves to true', () async {
      final api = ContactsApi(
        requestPermission: () async => PermissionStatus.granted,
      );

      expect(await api.requestPermission(), isTrue);
    });

    test("iOS 18+'s limited status also resolves to true", () async {
      final api = ContactsApi(
        requestPermission: () async => PermissionStatus.limited,
      );

      expect(await api.requestPermission(), isTrue);
    });

    test('denied resolves to false', () async {
      final api = ContactsApi(
        requestPermission: () async => PermissionStatus.denied,
      );

      expect(await api.requestPermission(), isFalse);
    });

    test('permanentlyDenied resolves to false', () async {
      final api = ContactsApi(
        requestPermission: () async => PermissionStatus.permanentlyDenied,
      );

      expect(await api.requestPermission(), isFalse);
    });
  });

  group('pickContact', () {
    test('a contact with a name and phone number is returned', () async {
      final api = ContactsApi(
        showPicker: () async => _contact(
          displayName: 'Priya Singh',
          phones: const [Phone(number: '9999999999')],
        ),
      );

      final picked = await api.pickContact();

      expect(picked?.name, 'Priya Singh');
      expect(picked?.phone, '9999999999');
    });

    test('only the first phone number is used when a contact has several', () async {
      final api = ContactsApi(
        showPicker: () async => _contact(
          displayName: 'Priya Singh',
          phones: const [Phone(number: '9999999999'), Phone(number: '8888888888')],
        ),
      );

      final picked = await api.pickContact();

      expect(picked?.phone, '9999999999');
    });

    test('a cancelled picker (null) resolves to null', () async {
      final api = ContactsApi(showPicker: () async => null);

      expect(await api.pickContact(), isNull);
    });

    test('a contact with no phone number resolves to null', () async {
      final api = ContactsApi(
        showPicker: () async => _contact(displayName: 'Priya Singh'),
      );

      expect(await api.pickContact(), isNull);
    });

    test('a contact with no display name resolves to null', () async {
      final api = ContactsApi(
        showPicker: () async =>
            _contact(phones: const [Phone(number: '9999999999')]),
      );

      expect(await api.pickContact(), isNull);
    });

    test('a contact with a blank display name resolves to null', () async {
      final api = ContactsApi(
        showPicker: () async => _contact(
          displayName: '   ',
          phones: const [Phone(number: '9999999999')],
        ),
      );

      expect(await api.pickContact(), isNull);
    });
  });
}
