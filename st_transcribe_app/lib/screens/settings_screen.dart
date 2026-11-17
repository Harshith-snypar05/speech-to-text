import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:record/record.dart';

import '../services/app_settings.dart';
import '../config/app_config.dart';
import '../services/auth_service.dart';
import '../services/platform_api.dart';
import '../theme.dart';
import 'help_screens.dart';
import 'settings_sections.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  // Only shown on native builds -- the web app auto-detects its backend
  // from the page's own address (see detectSameOriginBackendUrl), but a
  // native build isn't hosted anywhere, so there's no address to detect
  // this from. Someone has to type it in once.
  final _urlController = TextEditingController(
    text: AppSettings.backendUrl.value,
  );
  String? _urlError;

  /// Server-held preferences (same record the website edits). Null until loaded / offline.
  ServerSettings? _server;

  @override
  void initState() {
    super.initState();
    if (AppConfig.platformMode) _loadServerSettings();
  }

  Future<void> _loadServerSettings() async {
    try {
      final s = await PlatformApi.settings();
      if (!mounted) return;
      // The account's saved theme / auto-lock win over the device's local copy, like on the website.
      final mode = ThemeMode.values.firstWhere((m) => m.name == s.theme, orElse: () => AppSettings.themeMode.value);
      await AppSettings.setThemeMode(mode);
      await AppSettings.setPreventAutoLock(s.preventAutoLock);
      if (mounted) setState(() => _server = s);
    } catch (_) {
      // offline: local settings still work
    }
  }

  /// Saves a partial update to the account; returns the stored settings, or null on failure.
  Future<ServerSettings?> _saveServer(Map<String, dynamic> patch) async {
    try {
      final s = await PlatformApi.saveSettings(patch);
      if (mounted) setState(() => _server = s);
      return s;
    } catch (_) {
      return null;
    }
  }

  Future<void> _pickLanguage() async {
    final s = _server;
    if (s == null || s.supportedLanguages.isEmpty) return;
    final picked = await _showOptionSheet<String>(
      context: context,
      title: 'Language',
      options: [for (final l in s.supportedLanguages) _Option(value: l, label: _languageLabel(l))],
      selected: s.language,
    );
    if (picked != null && picked != s.language) await _saveServer({'language': picked});
  }

  static String _languageLabel(String code) => code == 'en' ? 'English' : code;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  void _submitUrl() {
    final value = _urlController.text.trim();
    if (!isValidBackendUrl(value)) {
      setState(
        () => _urlError = 'Must be a ws:// or wss:// address, e.g. wss://your-tunnel.trycloudflare.com',
      );
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
    if (picked != null) {
      await AppSettings.setThemeMode(picked);
      if (AppConfig.platformMode) _saveServer({'theme': picked.name});
    }
  }

  void _push(Widget page) => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page));

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
    if (picked == null && AppSettings.micDeviceId.value == null)
      return; // no change, both "Default"
    final label = picked == null
        ? null
        : devices.firstWhere((d) => d.id == picked).label;
    await AppSettings.setMicDevice(picked, label);
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Settings',
          style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18),
        ),
        automaticallyImplyLeading: false,
        leading: Navigator.of(context).canPop() ? BackButton(color: colors.textPrimary) : null,
      ),
      body: AnimatedBuilder(
        animation: Listenable.merge([
          AppSettings.textSize,
          AppSettings.themeMode,
          AppSettings.micDeviceLabel,
          AppSettings.backendUrl,
        ]),
        builder: (context, _) {
          return ListView(
            padding: EdgeInsets.zero,
            children: [
              const SizedBox(height: 4),
              if (AppConfig.platformMode) ...[
                const AccountSection(),
                const PasswordSection(),
              ],
              SettingsSection(
                title: 'Preferences',
                children: [
                  Row(
                    children: [
                      Icon(Icons.text_fields, color: colors.textSecondary, size: 20),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Text(
                          'Text size',
                          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: colors.textPrimary),
                        ),
                      ),
                      _segmented(
                        colors: colors,
                        options: const ['S', 'M', 'L'],
                        selected: AppTextSize.values.indexOf(AppSettings.textSize.value),
                        compact: true,
                        onChanged: (i) => AppSettings.setTextSize(AppTextSize.values[i]),
                      ),
                    ],
                  ),
                  Divider(height: 24, color: colors.cardBorder),
                  _settingsRow(
                    colors: colors,
                    icon: Icons.brightness_6_outlined,
                    label: 'Theme',
                    value: _themeLabel(AppSettings.themeMode.value),
                    onTap: _pickTheme,
                  ),
                  if (AppConfig.platformMode && _server != null) ...[
                    Divider(height: 1, color: colors.cardBorder),
                    _settingsRow(
                      colors: colors,
                      icon: Icons.language,
                      label: 'Language',
                      value: _languageLabel(_server!.language),
                      onTap: _pickLanguage,
                    ),
                  ],
                  Divider(height: 1, color: colors.cardBorder),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    secondary: Icon(Icons.screen_lock_portrait_outlined, color: colors.textSecondary),
                    title: const Text('Prevent auto-lock while live'),
                    subtitle: const Text('Keeps the screen on during a session.'),
                    value: AppSettings.preventAutoLock.value,
                    onChanged: (v) async {
                      await AppSettings.setPreventAutoLock(v);
                      if (AppConfig.platformMode) _saveServer({'prevent_auto_lock': v});
                      if (mounted) setState(() {});
                    },
                  ),
                ],
              ),
              if (AppConfig.platformMode) ...[
                const UsageSection(),
                if (_server != null) LimitsSection(settings: _server!, onSave: _saveServer),
                const MembershipSection(),
              ],
              SettingsSection(
                title: 'Microphone',
                children: [
                  _settingsRow(
                    colors: colors,
                    icon: Icons.mic_none,
                    label: 'Input device',
                    value: AppSettings.micDeviceLabel.value ?? 'Default',
                    onTap: _pickMicrophone,
                  ),
                ],
              ),
              if (!kIsWeb && !AppConfig.platformMode)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Divider(height: 32, color: colors.cardBorder),
                      Text('Connection', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: colors.textPrimary)),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          Icon(Icons.dns_outlined, color: colors.textSecondary, size: 20),
                          const SizedBox(width: 14),
                          Expanded(
                            child: TextField(
                              controller: _urlController,
                              onSubmitted: (_) => _submitUrl(),
                              style: TextStyle(fontSize: 14, color: colors.textPrimary),
                              decoration: InputDecoration(
                                labelText: 'Backend address',
                                hintText: 'wss://your-tunnel.trycloudflare.com',
                                errorText: _urlError,
                                border: const OutlineInputBorder(),
                                suffixIcon: IconButton(icon: const Icon(Icons.check), onPressed: _submitUrl),
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text('The address of the computer running the transcription server.', style: TextStyle(color: colors.textSecondary, fontSize: 12)),
                    ],
                  ),
                ),
              SettingsSection(
                title: 'Help',
                children: [
                  _settingsRow(
                    colors: colors,
                    icon: Icons.lightbulb_outline,
                    label: 'Request a feature',
                    value: '',
                    onTap: () => _push(const RequestFeatureScreen()),
                  ),
                  Divider(height: 1, color: colors.cardBorder),
                  _settingsRow(
                    colors: colors,
                    icon: Icons.wifi_off_outlined,
                    label: 'Fix a connection issue',
                    value: '',
                    onTap: () => _push(const ConnectionHelpScreen()),
                  ),
                  Divider(height: 1, color: colors.cardBorder),
                  _settingsRow(
                    colors: colors,
                    icon: Icons.privacy_tip_outlined,
                    label: 'Privacy Policy',
                    value: '',
                    onTap: () => _push(const LegalScreen(privacy: true)),
                  ),
                  Divider(height: 1, color: colors.cardBorder),
                  _settingsRow(
                    colors: colors,
                    icon: Icons.description_outlined,
                    label: 'Terms & Conditions',
                    value: '',
                    onTap: () => _push(const LegalScreen(privacy: false)),
                  ),
                ],
              ),
              if (AppConfig.platformMode) const AccountActionsSection(),
              Container(height: 8, color: colors.neutralChipBg),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
                child: OutlinedButton.icon(
                  onPressed: _logout,
                  icon: const Icon(Icons.logout),
                  label: const Text('Log out'),
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size.fromHeight(50),
                    foregroundColor: colors.recordRed,
                    side: BorderSide(color: colors.recordRed.withValues(alpha: 0.5)),
                  ),
                ),
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
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                  color: colors.textPrimary,
                ),
              ),
            ),
            if (value.isNotEmpty)
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 150),
                child: Text(
                  value,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.right,
                  style: TextStyle(color: colors.textSecondary, fontSize: 14),
                ),
              ),
            const SizedBox(width: 4),
            const SettingsChevron(),
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
      decoration: BoxDecoration(
        color: colors.neutralChipBg,
        borderRadius: BorderRadius.circular(10),
      ),
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
                  padding: EdgeInsets.symmetric(
                    vertical: compact ? 6 : 10,
                    horizontal: compact ? 14 : 4,
                  ),
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
                decoration: BoxDecoration(
                  color: colors.sheetHandle,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            Text(
              title,
              style: TextStyle(
                fontWeight: FontWeight.w800,
                fontSize: 17,
                color: colors.textPrimary,
              ),
            ),
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
                            Text(
                              o.label,
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w600,
                                color: colors.textPrimary,
                              ),
                            ),
                            if (o.subtitle != null)
                              Text(
                                o.subtitle!,
                                style: TextStyle(
                                  fontSize: 12,
                                  color: colors.textSecondary,
                                ),
                              ),
                          ],
                        ),
                      ),
                      if (o.value == selected)
                        Icon(Icons.check, color: colors.primaryBlue),
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
