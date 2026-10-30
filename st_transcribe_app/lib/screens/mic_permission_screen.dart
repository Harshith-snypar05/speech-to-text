import 'package:flutter/material.dart';
import '../theme.dart';
import '../widgets/st_logo.dart';

class MicPermissionScreen extends StatelessWidget {
  const MicPermissionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: Column(
            children: [
              const SizedBox(height: 40),
              const StLogo(size: 56),
              const SizedBox(height: 40),
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(color: AppColors.lightBlueBg, borderRadius: BorderRadius.circular(20)),
                child: const Icon(Icons.mic, color: AppColors.primaryBlue, size: 34),
              ),
              const SizedBox(height: 24),
              const Text('Microphone Access',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AppColors.textPrimary)),
              const SizedBox(height: 10),
              const Text(
                'We need microphone access to transcribe your speech in real time.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textSecondary, fontSize: 14, height: 1.4),
              ),
              const SizedBox(height: 32),
              const _FeatureRow(
                icon: Icons.bolt,
                title: 'Real-time transcription',
                subtitle: 'See your words as you speak',
              ),
              const SizedBox(height: 20),
              const _FeatureRow(
                icon: Icons.lock_outline,
                title: 'Private and secure',
                subtitle: 'No account needed',
              ),
              const SizedBox(height: 20),
              const _FeatureRow(
                icon: Icons.description_outlined,
                title: 'Saved automatically',
                subtitle: 'Your transcripts are stored locally',
              ),
              const Spacer(),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.primaryBlue,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
                  onPressed: () => Navigator.of(context).pushReplacementNamed('/session'),
                  child: const Text('Continue', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                ),
              ),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}

class _FeatureRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  const _FeatureRow({required this.icon, required this.title, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: AppColors.primaryBlue, size: 22),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
              Text(subtitle, style: const TextStyle(color: AppColors.textSecondary, fontSize: 13)),
            ],
          ),
        ),
      ],
    );
  }
}
