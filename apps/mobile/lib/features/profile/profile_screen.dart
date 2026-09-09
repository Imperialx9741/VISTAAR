import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/customer_api.dart';
import '../../shared/widgets/primary_button.dart';

/// User Profile — the User-side counterpart to
/// [SarthiOnboardingScreen]'s profile section, built 2026-09-04 to close
/// this app's next highest-priority gap (profile/ride history/
/// promotions/referrals — none had any mobile code before this change,
/// even though every one of these backend endpoints has existed for a
/// while). `GET /api/v1/customers/me` (api-contracts.md §8) always
/// succeeds for a signed-in customer — auto-provisioning, unlike the
/// Sarthi equivalent — so there is no "not started" state to render
/// here, only a normal edit form.
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  CustomerProfile? _profile;
  bool _isLoading = true;
  bool _isSaving = false;
  String? _errorMessage;

  final _fullNameController = TextEditingController();
  bool _notificationEnabled = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _fullNameController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final profile = await context.read<CustomerApi>().getProfile();
      if (!mounted) return;
      setState(() {
        _profile = profile;
        _fullNameController.text = profile.fullName ?? '';
        _notificationEnabled = profile.notificationEnabled;
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _save() async {
    setState(() => _isSaving = true);
    try {
      final profile = await context.read<CustomerApi>().updateProfile(
        fullName: _fullNameController.text.trim(),
        notificationEnabled: _notificationEnabled,
      );
      if (!mounted) return;
      setState(() => _profile = profile);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Profile updated.')));
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: SafeArea(
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : _profile == null
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _errorMessage ?? 'Could not load your profile.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              )
            : RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(_profile!.phone),
                      subtitle: const Text('Phone number'),
                      leading: const Icon(Icons.phone_outlined),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: _fullNameController,
                      decoration: const InputDecoration(
                        labelText: 'Full name',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 16),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Notifications'),
                      value: _notificationEnabled,
                      onChanged: (value) =>
                          setState(() => _notificationEnabled = value),
                    ),
                    const SizedBox(height: 16),
                    PrimaryButton(
                      label: 'Save',
                      isLoading: _isSaving,
                      onPressed: _save,
                    ),
                  ],
                ),
              ),
      ),
    );
  }
}
