import 'package:flutter/material.dart';
import 'package:record/record.dart';
import '../services/app_settings.dart';
import '../services/auth_service.dart';
import '../theme.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _urlController = TextEditingController(text: AppSettings.backendUrl.value);
  String? _urlError;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _pickEngine(AppColors colors) async {
    final picked = await _showOptionSheet<TranscriptionEnginePreset>(
      context: context,
      title: 'Transcription Engine',
      options: [
        for (final p in TranscriptionEnginePreset.values)
          _Option(value: p, label: p.label, subtitle: p == TranscriptionEnginePreset.custom ? null : p.defaultUrl),
      ],
      selected: AppSettings.enginePreset.value,
    );
    if (picked == null) return;
    await AppSettings.setEnginePreset(picked);
    _urlController.text = AppSettings.backendUrl.value;
    setState(() => _urlError = null);
  }

  void _submitUrl() {
    final value = _urlController.text.trim();
    if (!isValidBackendUrl(value)) {
      setState(() => _urlError = 'Must be a ws:// or wss:// URL, e.g. ws://localhost:8767');
      return;
    }
    setState(() => _urlError = null);
    AppSettings.setBackendUrl(value);
    FocusScope.of(context).unfocus();
  }

  Future<void> _pickTheme() async {
    final picked = await _showOptionSheet<ThemeMode>(
      context: context,
      title: 'Theme',
      options: const [
        _Option(value: ThemeMode.system, label: 'System'),
        _Option(value: ThemeMode.light, label: 'Light'),
        _Option(value: ThemeMode.dark, label: 'Dark'),
      ],
      selected: AppSettings.themeMode.value,
    );
    if (picked != null) await AppSettings.setThemeMode(picked);
  }

  Future<void> _logout() async {
    await AuthService.logout();
    if (!mounted) return;
    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  Future<void> _pickMicrophone() async {
    List<InputDevice> devices;
    try {
      devices = await AudioRecorder().listInputDevices();
    } catch (_) {
      devices = const [];
    }
    if (!mounted) return;
    if (devices.isEmpty) {
      // Not supported on this platform -- nothing to pick, row stays
      // informational-only (matches "where supported").
      return;
    }
    final picked = await _showOptionSheet<String?>(
      context: context,
      title: 'Microphone',
      options: [
        const _Option(value: null, label: 'Default'),
        for (final d in devices) _Option(value: d.id, label: d.label),
      ],
      selected: AppSettings.micDeviceId.value,
    );
    if (picked == null && AppSettings.micDeviceId.value == null) return; // no change, both "Default"
    final label = picked == null ? null : devices.firstWhere((d) => d.id == picked).label;
    await AppSettings.setMicDevice(picked, label);
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
        leading: BackButton(color: colors.textPrimary),
        actions: [
          IconButton(icon: Icon(Icons.close, color: colors.textPrimary), onPressed: () => Navigator.of(context).pop()),
        ],
      ),
      body: AnimatedBuilder(
        animation: Listenable.merge([
          AppSettings.transcriptionMode,
          AppSettings.textSize,
          AppSettings.enginePreset,
          AppSettings.backendUrl,
          AppSettings.themeMode,
          AppSettings.micDeviceLabel,
          AuthService.currentEmail,
        ]),
        builder: (context, _) {
          return ListView(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            children: [
              Text('Transcription mode', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: colors.textPrimary)),
              const SizedBox(height: 10),
              _segmented(
                colors: colors,
                options: const ['Live\n(word-by-word)', 'Accurate\n(per-sentence)'],
                selected: AppSettings.transcriptionMode.value == TranscriptionMode.live ? 0 : 1,
                onChanged: (i) => AppSettings.setTranscriptionMode(i == 0 ? TranscriptionMode.live : TranscriptionMode.accurate),
              ),
              const SizedBox(height: 20),
              Row(
                children: [
                  Icon(Icons.text_fields, color: colors.textSecondary, size: 20),
                  const SizedBox(width: 14),
                  Expanded(child: Text('Text size', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: colors.textPrimary))),
                  _segmented(
                    colors: colors,
                    options: const ['S', 'M', 'L'],
                    selected: AppTextSize.values.indexOf(AppSettings.textSize.value),
                    compact: true,
                    onChanged: (i) => AppSettings.setTextSize(AppTextSize.values[i]),
                  ),
                ],
              ),
              Divider(height: 32, color: colors.cardBorder),
              Text('Backend', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: colors.textPrimary)),
              const SizedBox(height: 4),
              _settingsRow(
                colors: colors,
                icon: Icons.dns_outlined,
                label: 'Transcription Engine',
                value: AppSettings.enginePreset.value.label,
                onTap: () => _pickEngine(colors),
              ),
              if (AppSettings.enginePreset.value == TranscriptionEnginePreset.custom) ...[
                const SizedBox(height: 10),
                TextField(
                  controller: _urlController,
                  onSubmitted: (_) => _submitUrl(),
                  style: TextStyle(fontSize: 14, color: colors.textPrimary),
                  decoration: InputDecoration(
                    labelText: 'Backend URL',
                    hintText: 'wss://your-server.example.com',
                    errorText: _urlError,
                    border: const OutlineInputBorder(),
                    suffixIcon: IconButton(icon: const Icon(Icons.check), onPressed: _submitUrl),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'ws:// works for local development; use wss:// for anything outside localhost.',
                  style: TextStyle(color: colors.textSecondary, fontSize: 12),
                ),
              ] else ...[
                const SizedBox(height: 4),
                Padding(
                  padding: const EdgeInsets.only(left: 34),
                  child: Text(AppSettings.backendUrl.value, style: TextStyle(color: colors.textSecondary, fontSize: 12)),
                ),
              ],
              Divider(height: 32, color: colors.cardBorder),
              _settingsRow(colors: colors, icon: Icons.brightness_6_outlined, label: 'Theme', value: _themeLabel(AppSettings.themeMode.value), onTap: _pickTheme),
              Divider(height: 1, color: colors.cardBorder),
              _settingsRow(
                colors: colors,
                icon: Icons.mic_none,
                label: 'Microphone',
                value: AppSettings.micDeviceLabel.value ?? 'Default',
                onTap: _pickMicrophone,
              ),
              Divider(height: 32, color: colors.cardBorder),
              _settingsRow(
                colors: colors,
                icon: Icons.logout,
                label: 'Log out',
                value: AuthService.currentEmail.value ?? '',
                onTap: _logout,
              ),
            ],
          );
        },
      ),
    );
  }

  String _themeLabel(ThemeMode mode) => switch (mode) {
        ThemeMode.system => 'System',
        ThemeMode.light => 'Light',
        ThemeMode.dark => 'Dark',
      };

  Widget _settingsRow({
    required AppColors colors,
    required IconData icon,
    required String label,
    required String value,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14),
        child: Row(
          children: [
            Icon(icon, color: colors.textSecondary, size: 20),
            const SizedBox(width: 14),
            Expanded(child: Text(label, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: colors.textPrimary))),
            Flexible(
              child: Text(value,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.right,
                  style: TextStyle(color: colors.textSecondary, fontSize: 14)),
            ),
            const SizedBox(width: 4),
            Icon(Icons.chevron_right, color: colors.textSecondary, size: 18),
          ],
        ),
      ),
    );
  }

  Widget _segmented({
    required AppColors colors,
    required List<String> options,
    required int selected,
    required ValueChanged<int> onChanged,
    bool compact = false,
  }) {
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: colors.neutralChipBg, borderRadius: BorderRadius.circular(10)),
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
                    color: selected == i ? colors.header : Colors.transparent,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    options[i],
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: compact ? 13 : 12,
                      fontWeight: FontWeight.w700,
                      color: selected == i ? Colors.white : colors.textPrimary,
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

class _Option<T> {
  final T value;
  final String label;
  final String? subtitle;
  const _Option({required this.value, required this.label, this.subtitle});
}

Future<T?> _showOptionSheet<T>({
  required BuildContext context,
  required String title,
  required List<_Option<T>> options,
  required T selected,
}) {
  final colors = AppColors.of(context);
  return showModalBottomSheet<T>(
    context: context,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) {
      return Container(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        decoration: BoxDecoration(
          color: colors.surface,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(color: colors.sheetHandle, borderRadius: BorderRadius.circular(2)),
              ),
            ),
            Text(title, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17, color: colors.textPrimary)),
            const SizedBox(height: 8),
            for (final o in options)
              InkWell(
                onTap: () => Navigator.of(sheetContext).pop(o.value),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(o.label, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: colors.textPrimary)),
                            if (o.subtitle != null)
                              Text(o.subtitle!, style: TextStyle(fontSize: 12, color: colors.textSecondary)),
                          ],
                        ),
                      ),
                      if (o.value == selected) Icon(Icons.check, color: colors.primaryBlue),
                    ],
                  ),
                ),
              ),
          ],
        ),
      );
    },
  );
}
