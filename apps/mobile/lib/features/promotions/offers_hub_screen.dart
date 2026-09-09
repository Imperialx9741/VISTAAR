import 'package:flutter/material.dart';

import '../../shared/design/vistaar_card.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../referrals/referral_screen.dart';
import 'promotions_screen.dart';

/// The User role's Offers tab (Phase 3 of the redesign, navigation
/// shell, 2026-09-08) — groups two screens that already existed
/// (Promotions, Referrals) under one entry point instead of two
/// separate AppBar icons on the Home tab, per the Phase 1 audit's
/// proposed navigation. Both destination screens are unchanged; this
/// is purely a menu.
class OffersHubScreen extends StatelessWidget {
  const OffersHubScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Offers')),
      body: ListView(
        padding: const EdgeInsets.all(VistaarSpacing.md),
        children: [
          VistaarCard(
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const PromotionsScreen()),
            ),
            child: _HubRow(
              icon: Icons.local_offer_outlined,
              // Golden yellow — "promotional elements" per the owner's
              // brand brief; this whole screen is promotional, so both
              // rows get it, not just one arbitrarily.
              iconColor: Theme.of(context).colorScheme.tertiary,
              title: 'Promotions',
              subtitle: 'Offers and discounts available to you',
            ),
          ),
          const SizedBox(height: VistaarSpacing.sm),
          VistaarCard(
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const ReferralScreen()),
            ),
            child: _HubRow(
              icon: Icons.card_giftcard_outlined,
              iconColor: Theme.of(context).colorScheme.tertiary,
              title: 'Refer & Earn',
              subtitle: 'Invite friends and track your referral rewards',
            ),
          ),
        ],
      ),
    );
  }
}

class _HubRow extends StatelessWidget {
  const _HubRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.iconColor,
  });

  final IconData icon;
  final Color? iconColor;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        Icon(icon, color: iconColor ?? theme.colorScheme.primary),
        const SizedBox(width: VistaarSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: theme.textTheme.titleMedium),
              Text(
                subtitle,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
        Icon(Icons.chevron_right, color: theme.colorScheme.onSurfaceVariant),
      ],
    );
  }
}
