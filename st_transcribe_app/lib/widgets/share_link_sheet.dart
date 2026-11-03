import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import '../theme.dart';

/// Matches the "Live Transcript Link" sheet from the reference design.
/// "Share Link" hands off to the OS-native share sheet via share_plus.
class ShareLinkSheet extends StatelessWidget {
  final String link;
  final String? accessCode;
  const ShareLinkSheet({super.key, required this.link, this.accessCode});

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 32),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 36,
            height: 4,
            margin: const EdgeInsets.only(bottom: 20),
            decoration: BoxDecoration(color: colors.cardBorder, borderRadius: BorderRadius.circular(2)),
          ),
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(color: colors.lightBlueBg, shape: BoxShape.circle),
            child: Icon(Icons.link, color: colors.primaryBlue),
          ),
          const SizedBox(height: 16),
          Text('Live Transcript Link',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17, color: colors.textPrimary)),
          const SizedBox(height: 8),
          Text(
            accessCode == null
                ? 'Anyone with this link can watch the live transcript. The link will stop working when you end the session.'
                : 'Anyone with this link can watch the live transcript -- the access code is already baked in. Stops working when you end the session.',
            textAlign: TextAlign.center,
            style: TextStyle(color: colors.textSecondary, fontSize: 13, height: 1.4),
          ),
          if (accessCode != null) ...[
            const SizedBox(height: 10),
            Text('Access code: $accessCode',
                style: TextStyle(color: colors.textPrimary, fontSize: 13, fontWeight: FontWeight.w700)),
          ],
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: colors.neutralChipBg,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Icon(Icons.link, size: 16, color: colors.textSecondary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(link, style: TextStyle(fontSize: 13, color: colors.textPrimary)),
                ),
                InkWell(
                  onTap: () => Clipboard.setData(ClipboardData(text: link)),
                  child: Icon(Icons.copy_outlined, size: 16, color: colors.textSecondary),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: colors.primaryBlue,
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              ),
              onPressed: () => SharePlus.instance.share(ShareParams(
                text: 'Watch the live transcript: $link',
                subject: 'Live Transcript Link',
              )),
              icon: const Icon(Icons.ios_share, size: 18),
              label: const Text('Share Link', style: TextStyle(fontWeight: FontWeight.w700)),
            ),
          ),
          const SizedBox(height: 12),
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text('Done', style: TextStyle(color: colors.textPrimary, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}
