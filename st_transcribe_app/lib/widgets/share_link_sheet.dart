import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import '../theme.dart';

/// Matches the "Live Transcript Link" sheet from the reference design.
/// "Share Link" hands off to the OS-native share sheet via share_plus.
class ShareLinkSheet extends StatelessWidget {
  final String link;
  const ShareLinkSheet({super.key, required this.link});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 32),
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 36,
            height: 4,
            margin: const EdgeInsets.only(bottom: 20),
            decoration: BoxDecoration(color: AppColors.cardBorder, borderRadius: BorderRadius.circular(2)),
          ),
          Container(
            width: 56,
            height: 56,
            decoration: const BoxDecoration(color: AppColors.lightBlueBg, shape: BoxShape.circle),
            child: const Icon(Icons.link, color: AppColors.primaryBlue),
          ),
          const SizedBox(height: 16),
          const Text('Live Transcript Link', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 8),
          const Text(
            'Anyone with this link can watch the live transcript. The link will stop working when you end the session.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textSecondary, fontSize: 13, height: 1.4),
          ),
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: const Color(0xFFF3F4F6),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                const Icon(Icons.link, size: 16, color: AppColors.textSecondary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(link, style: const TextStyle(fontSize: 13, color: AppColors.textPrimary)),
                ),
                InkWell(
                  onTap: () => Clipboard.setData(ClipboardData(text: link)),
                  child: const Icon(Icons.copy_outlined, size: 16, color: AppColors.textSecondary),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.primaryBlue,
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
            child: const Text('Done', style: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}
