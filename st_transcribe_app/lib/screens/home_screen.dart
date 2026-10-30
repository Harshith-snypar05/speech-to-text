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
  late Future<List<Transcript>> _transcripts;

  @override
  void initState() {
    super.initState();
    _transcripts = _load();
  }

  Future<List<Transcript>> _load() => TranscriptStorage.list();

  Future<void> _refresh() async {
    final next = _load();
    await next;
    setState(() => _transcripts = next);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              color: AppColors.darkHeader,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.chevron_left, color: Colors.white),
                    onPressed: () {},
                  ),
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
                child: FutureBuilder<List<Transcript>>(
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
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: const [
                            Text('Recent Transcripts',
                                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: AppColors.textPrimary)),
                            Icon(Icons.search, color: AppColors.textPrimary),
                          ],
                        ),
                        const SizedBox(height: 12),
                        if (snapshot.connectionState == ConnectionState.waiting)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 32),
                            child: Center(child: CircularProgressIndicator()),
                          )
                        else if (transcripts.isEmpty)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 32),
                            child: Center(
                              child: Text('No transcripts yet. Start a session to create one.',
                                  style: TextStyle(color: AppColors.textSecondary)),
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
      color: AppColors.primaryBlue,
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
              decoration: BoxDecoration(color: AppColors.lightBlueBg, borderRadius: BorderRadius.circular(8)),
              child: const Icon(Icons.description_outlined, size: 18, color: AppColors.primaryBlue),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                  const SizedBox(height: 2),
                  Text(preview,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: AppColors.textSecondary, fontSize: 13)),
                  const SizedBox(height: 2),
                  Text(date, style: const TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                ],
              ),
            ),
            PopupMenuButton<void>(
              icon: const Icon(Icons.more_horiz, color: AppColors.textSecondary),
              itemBuilder: (context) => [
                PopupMenuItem(
                  onTap: onDownload,
                  child: const Row(
                    children: [
                      Icon(Icons.download_outlined, size: 18, color: AppColors.textPrimary),
                      SizedBox(width: 10),
                      Text('Download'),
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
