import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/transcript.dart';
import '../services/auth_service.dart';
import '../services/platform_api.dart';
import '../services/transcript_storage.dart';
import '../theme.dart';
import 'history_screen.dart';

/// Home tab: greeting, start card, recent transcripts. In platform mode the list comes from the backend
/// (the signed-in account's own sessions); otherwise from local storage.
class HomeScreen extends StatefulWidget {
  final VoidCallback? onStartRecording;
  final VoidCallback? onSeeAll;
  const HomeScreen({super.key, this.onStartRecording, this.onSeeAll});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<List<HistoryItem>> _items;
  Future<UsageInfo>? _usage;

  @override
  void initState() {
    super.initState();
    _items = loadHistory();
    if (AppConfig.platformMode) _usage = PlatformApi.usage();
  }

  Future<void> _refresh() async {
    final next = loadHistory();
    setState(() {
      _items = next;
      if (AppConfig.platformMode) _usage = PlatformApi.usage();
    });
    try {
      await next;
    } catch (_) {}
  }

  String get _name {
    final e = AuthService.currentEmail.value ?? '';
    final local = e.split('@').first.replaceAll(RegExp(r'[._]'), ' ').trim();
    if (local.isEmpty) return 'there';
    return local.split(' ').map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}').join(' ');
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 100),
          children: [
            Text('Hello, $_name', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: c.textPrimary)),
            const SizedBox(height: 4),
            Text('Ready to transcribe?', style: TextStyle(color: c.textSecondary)),
            const SizedBox(height: 20),
            _StartCard(onTap: widget.onStartRecording),
            if (_usage != null) ...[const SizedBox(height: 16), UsageCard(future: _usage!)],
            const SizedBox(height: 28),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Recent transcripts', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: c.textPrimary)),
                TextButton(onPressed: widget.onSeeAll, child: const Text('See all')),
              ],
            ),
            FutureBuilder<List<HistoryItem>>(
              future: _items,
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Padding(padding: EdgeInsets.all(32), child: Center(child: CircularProgressIndicator()));
                }
                if (snap.hasError) {
                  return _Note(text: 'Could not load your transcripts. Pull down to retry. Your data is unchanged.', color: c.recordRed);
                }
                final items = snap.data ?? const <HistoryItem>[];
                if (items.isEmpty) return _Note(text: 'No transcripts yet. Tap the microphone to record your first one.', color: c.textSecondary);
                return Column(children: [for (final i in items.take(4)) HistoryTile(item: i)]);
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _Note extends StatelessWidget {
  final String text;
  final Color color;
  const _Note({required this.text, required this.color});
  @override
  Widget build(BuildContext context) =>
      Padding(padding: const EdgeInsets.symmetric(vertical: 28), child: Center(child: Text(text, textAlign: TextAlign.center, style: TextStyle(color: color))));
}

class _StartCard extends StatelessWidget {
  final VoidCallback? onTap;
  const _StartCard({this.onTap});
  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: Ink(
        decoration: BoxDecoration(gradient: brandGradient, borderRadius: BorderRadius.circular(20)),
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: onTap,
          child: const Padding(
            padding: EdgeInsets.all(20),
            child: Row(
              children: [
                Icon(Icons.mic, color: Colors.white, size: 32),
                SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('Start recording', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w800)),
                    SizedBox(height: 2),
                    Text('The microphone is used only while you record.', style: TextStyle(color: Colors.white70, fontSize: 13)),
                  ]),
                ),
                Icon(Icons.chevron_right, color: Colors.white),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// One row in a transcripts list; either a platform session or a local transcript.
class HistoryItem {
  final String id;
  final String title;
  final String subtitle;
  final TranscriptMeta? local;
  final SessionItem? platform;
  const HistoryItem({required this.id, required this.title, required this.subtitle, this.local, this.platform});
}

String _fmtMin(double seconds) {
  final m = (seconds / 60).floor();
  return '$m min';
}

/// Plan, remaining minutes, add-on balance, reset date and any usage warnings.
class UsageCard extends StatelessWidget {
  final Future<UsageInfo> future;
  const UsageCard({super.key, required this.future});
  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return FutureBuilder<UsageInfo>(
      future: future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) return const SizedBox(height: 90, child: Center(child: CircularProgressIndicator()));
        if (snap.hasError) return Text('Usage is unavailable right now. Pull down to retry.', style: TextStyle(color: c.textSecondary, fontSize: 13));
        final u = snap.data!;
        final reset = '${u.resetAt.year}-${_two(u.resetAt.month)}-${_two(u.resetAt.day)}';
        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(16), border: Border.all(color: c.cardBorder)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Text('${u.planName} plan', style: TextStyle(fontWeight: FontWeight.w700, color: c.textPrimary)),
              Text('Resets $reset', style: TextStyle(color: c.textSecondary, fontSize: 12)),
            ]),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(value: (u.percentUsed / 100).clamp(0, 1).toDouble(), minHeight: 8),
            ),
            const SizedBox(height: 8),
            Text('${_fmtMin(u.includedRemainingSeconds)} of ${u.includedMinutes} min left'
                '${u.addonRemainingSeconds > 0 ? ' · add-on ${_fmtMin(u.addonRemainingSeconds)}' : ''}',
                style: TextStyle(color: c.textSecondary, fontSize: 13)),
            for (final w in u.warnings) Padding(padding: const EdgeInsets.only(top: 6), child: Text(w, style: TextStyle(color: c.recordRed, fontSize: 13))),
          ]),
        );
      },
    );
  }
}

String _two(int n) => n.toString().padLeft(2, '0');

String formatWhen(DateTime t) => '${formatDateLabel(t)}, ${_two(t.hour)}:${_two(t.minute)}';

Future<List<HistoryItem>> loadHistory() async {
  if (AppConfig.platformMode) {
    final s = await PlatformApi.sessions();
    return [
      for (final x in s)
        HistoryItem(
          id: x.id,
          title: x.title.isNotEmpty ? x.title : (x.startedAt != null ? formatWhen(x.startedAt!) : 'Session'),
          subtitle: '${x.startedAt != null ? formatWhen(x.startedAt!) : ''}${x.endedAt == null ? ' · in progress' : ''}${x.sharing ? ' · shared' : ''}',
          platform: x,
        ),
    ];
  }
  final l = await TranscriptStorage.listMeta();
  return [for (final m in l) HistoryItem(id: m.id, title: m.title, subtitle: '${m.dateLabel} · ${m.preview}', local: m)];
}
