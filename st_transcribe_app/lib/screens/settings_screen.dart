import 'package:flutter/material.dart';
import '../theme.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _liveMode = true; // true = Live (word-by-word), false = Accurate (per-sentence)
  int _textSize = 1; // 0=S, 1=M, 2=L

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
        leading: const BackButton(color: AppColors.textPrimary),
        actions: [IconButton(icon: const Icon(Icons.close, color: AppColors.textPrimary), onPressed: () => Navigator.of(context).pop())],
      ),
      body: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        children: [
          const Text('Transcription mode', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
          const SizedBox(height: 10),
          _segmented(
            options: const ['Live\n(word-by-word)', 'Accurate\n(per-sentence)'],
            selected: _liveMode ? 0 : 1,
            onChanged: (i) => setState(() => _liveMode = i == 0),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              const Icon(Icons.text_fields, color: AppColors.textSecondary, size: 20),
              const SizedBox(width: 14),
              const Expanded(child: Text('Text size', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14))),
              _segmented(
                options: const ['S', 'M', 'L'],
                selected: _textSize,
                compact: true,
                onChanged: (i) => setState(() => _textSize = i),
              ),
            ],
          ),
          const Divider(height: 32, color: AppColors.cardBorder),
          _settingsRow(icon: Icons.brightness_6_outlined, label: 'Theme', value: 'System'),
          const Divider(height: 1, color: AppColors.cardBorder),
          _settingsRow(icon: Icons.mic_none, label: 'Microphone', value: 'Default'),
        ],
      ),
    );
  }

  Widget _settingsRow({required IconData icon, required String label, required String value}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 14),
      child: Row(
        children: [
          Icon(icon, color: AppColors.textSecondary, size: 20),
          const SizedBox(width: 14),
          Expanded(child: Text(label, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14))),
          Text(value, style: const TextStyle(color: AppColors.textSecondary, fontSize: 14)),
          const SizedBox(width: 4),
          const Icon(Icons.chevron_right, color: AppColors.textSecondary, size: 18),
        ],
      ),
    );
  }

  Widget _segmented({
    required List<String> options,
    required int selected,
    required ValueChanged<int> onChanged,
    bool compact = false,
  }) {
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: const Color(0xFFF3F4F6), borderRadius: BorderRadius.circular(10)),
      child: Row(
        mainAxisSize: compact ? MainAxisSize.min : MainAxisSize.max,
        children: [
          for (int i = 0; i < options.length; i++)
            Expanded(
              flex: compact ? 0 : 1,
              child: GestureDetector(
                onTap: () => onChanged(i),
                child: Container(
                  margin: const EdgeInsets.symmetric(horizontal: 2),
                  padding: EdgeInsets.symmetric(vertical: compact ? 6 : 10, horizontal: compact ? 14 : 4),
                  decoration: BoxDecoration(
                    color: selected == i ? AppColors.darkHeader : Colors.transparent,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    options[i],
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: compact ? 13 : 12,
                      fontWeight: FontWeight.w700,
                      color: selected == i ? Colors.white : AppColors.textPrimary,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
