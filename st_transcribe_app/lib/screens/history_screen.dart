import 'package:flutter/material.dart';

import '../theme.dart';
import 'home_screen.dart';
import 'platform_session_screen.dart';

/// Transcripts tab: the signed-in account's saved sessions.
class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});
  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  late Future<List<HistoryItem>> _items = loadHistory();
  String _q = '';

  Future<void> _refresh() async {
    final next = loadHistory();
    setState(() => _items = next);
    try {
      await next;
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Transcripts', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: c.textPrimary)),
            const SizedBox(height: 12),
            TextField(
              onChanged: (v) => setState(() => _q = v.trim().toLowerCase()),
              decoration: InputDecoration(
                hintText: 'Search transcripts',
                prefixIcon: const Icon(Icons.search),
                filled: true,
                fillColor: c.surface,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: c.cardBorder)),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _refresh,
                child: FutureBuilder<List<HistoryItem>>(
                  future: _items,
                  builder: (context, snap) {
                    if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
                    if (snap.hasError) {
                      return ListView(children: [
                        Padding(padding: const EdgeInsets.all(32), child: Text('Could not load transcripts. Pull down to retry.', textAlign: TextAlign.center, style: TextStyle(color: c.recordRed))),
                      ]);
                    }
                    final all = snap.data ?? const <HistoryItem>[];
                    final items = _q.isEmpty ? all : all.where((i) => '${i.title} ${i.subtitle}'.toLowerCase().contains(_q)).toList();
                    if (items.isEmpty) {
                      return ListView(children: [
                        Padding(padding: const EdgeInsets.all(32), child: Text(all.isEmpty ? 'No transcripts yet.' : 'No matches.', textAlign: TextAlign.center, style: TextStyle(color: c.textSecondary))),
                      ]);
                    }
                    return ListView(padding: const EdgeInsets.only(bottom: 100), children: [for (final i in items) HistoryTile(item: i)]);
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class HistoryTile extends StatelessWidget {
  final HistoryItem item;
  const HistoryTile({super.key, required this.item});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Card(
      elevation: 0,
      color: c.surface,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: c.cardBorder)),
      child: ListTile(
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(color: c.lightBlueBg, borderRadius: BorderRadius.circular(10)),
          child: Icon(Icons.description_outlined, color: c.primaryBlue),
        ),
        title: Text(item.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(item.subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
        trailing: const Icon(Icons.chevron_right),
        onTap: () {
          if (item.platform != null) {
            Navigator.of(context).push(MaterialPageRoute(builder: (_) => PlatformSessionScreen(sessionId: item.platform!.id)));
          } else if (item.local != null) {
            Navigator.of(context).pushNamed('/transcript', arguments: item.local);
          }
        },
      ),
    );
  }
}
