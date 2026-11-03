import 'package:flutter/material.dart';
import '../models/transcript.dart';
import '../services/transcript_storage.dart';
import '../theme.dart';
import '../widgets/st_logo.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<List<TranscriptMeta>> _transcripts;

  @override
  void initState() {
    super.initState();
    _transcripts = _load();
  }

  Future<List<TranscriptMeta>> _load() => TranscriptStorage.listMeta();

  Future<void> _refresh() async {
    final next = _load();
    await next;
    setState(() => _transcripts = next);
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return Scaffold(
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              color: colors.header,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Row(
                children: [
                  const StLogo(size: 28),
                  const SizedBox(width: 8),
                  const Text(
                    'Transcribe',
                    style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.settings_outlined, color: Colors.white),
                    onPressed: () => Navigator.of(context).pushNamed('/settings'),
                  ),
                ],
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _refresh,
                child: FutureBuilder<List<TranscriptMeta>>(
                  future: _transcripts,
                  builder: (context, snapshot) {
                    final transcripts = snapshot.data ?? [];
                    return ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        _StartSessionButton(
                          onTap: () async {
                            await Navigator.of(context).pushNamed('/session');
                            _refresh();
                          },
                        ),
                        const SizedBox(height: 24),
                        Text('Recent Transcripts',
                            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: colors.textPrimary)),
                        const SizedBox(height: 12),
                        if (snapshot.connectionState == ConnectionState.waiting)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 32),
                            child: Center(child: CircularProgressIndicator()),
                          )
                        else if (transcripts.isEmpty)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 32),
                            child: Center(
                              child: Text('No transcripts yet. Start a session to create one.',
                                  style: TextStyle(color: colors.textSecondary)),
                            ),
                          )
                        else
                          for (final t in transcripts)
                            _TranscriptTile(
                              title: t.title,
                              preview: t.preview,
                              date: t.dateLabel,
                              onTap: () => Navigator.of(context).pushNamed('/transcript', arguments: t),
                              onDownload: () => TranscriptStorage.export(t),
                            ),
                      ],
                    );
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

class _StartSessionButton extends StatelessWidget {
  final VoidCallback onTap;
  const _StartSessionButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.of(context).primaryBlue,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 20, vertical: 18),
          child: Row(
            children: [
              Icon(Icons.mic, color: Colors.white),
              SizedBox(width: 12),
              Text('Start New Session',
                  style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700)),
              Spacer(),
              Icon(Icons.chevron_right, color: Colors.white),
            ],
          ),
        ),
      ),
    );
  }
}

class _TranscriptTile extends StatelessWidget {
  final String title;
  final String preview;
  final String date;
  final VoidCallback onTap;
  final VoidCallback onDownload;

  const _TranscriptTile({
    required this.title,
    required this.preview,
    required this.date,
    required this.onTap,
    required this.onDownload,
  });

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 36,
              height: 36,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: colors.lightBlueBg, borderRadius: BorderRadius.circular(8)),
              child: Icon(Icons.description_outlined, size: 18, color: colors.primaryBlue),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: colors.textPrimary)),
                  const SizedBox(height: 2),
                  Text(preview,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: colors.textSecondary, fontSize: 13)),
                  const SizedBox(height: 2),
                  Text(date, style: TextStyle(color: colors.textSecondary, fontSize: 12)),
                ],
              ),
            ),
            PopupMenuButton<void>(
              icon: Icon(Icons.more_horiz, color: colors.textSecondary),
              itemBuilder: (context) => [
                PopupMenuItem(
                  onTap: onDownload,
                  child: Row(
                    children: [
                      Icon(Icons.download_outlined, size: 18, color: colors.textPrimary),
                      const SizedBox(width: 10),
                      const Text('Download'),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
