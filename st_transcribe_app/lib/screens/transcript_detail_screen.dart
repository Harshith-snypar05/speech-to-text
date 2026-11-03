import 'package:flutter/material.dart';
import '../models/transcript.dart';
import '../services/transcript_storage.dart';
import '../theme.dart';

class TranscriptDetailScreen extends StatefulWidget {
  final TranscriptMeta meta;
  const TranscriptDetailScreen({super.key, required this.meta});

  @override
  State<TranscriptDetailScreen> createState() => _TranscriptDetailScreenState();
}

class _TranscriptDetailScreenState extends State<TranscriptDetailScreen> {
  late Future<String?> _body;

  @override
  void initState() {
    super.initState();
    _body = TranscriptStorage.loadBody(widget.meta.id);
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(color: colors.textPrimary),
        title: Text(widget.meta.title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
        actions: [
          PopupMenuButton<void>(
            icon: Icon(Icons.more_horiz, color: colors.textPrimary),
            itemBuilder: (context) => [
              PopupMenuItem(
                onTap: () => TranscriptStorage.export(widget.meta),
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
      body: FutureBuilder<String?>(
        future: _body,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          final body = snapshot.data;
          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Text(widget.meta.dateLabel, style: TextStyle(color: colors.textSecondary, fontSize: 13)),
              const SizedBox(height: 16),
              Text(
                body ?? 'This transcript could not be loaded.',
                style: TextStyle(fontSize: 15, height: 1.6, color: colors.textPrimary),
              ),
            ],
          );
        },
      ),
    );
  }
}
