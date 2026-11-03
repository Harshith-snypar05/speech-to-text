import 'package:flutter/material.dart';
import '../models/transcript.dart';
import '../services/transcript_storage.dart';
import '../theme.dart';

class TranscriptDetailScreen extends StatelessWidget {
  final Transcript transcript;
  const TranscriptDetailScreen({super.key, required this.transcript});

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(color: colors.textPrimary),
        title: Text(transcript.title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
        actions: [
          PopupMenuButton<void>(
            icon: Icon(Icons.more_horiz, color: colors.textPrimary),
            itemBuilder: (context) => [
              PopupMenuItem(
                onTap: () => TranscriptStorage.export(transcript),
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
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(transcript.dateLabel, style: TextStyle(color: colors.textSecondary, fontSize: 13)),
          const SizedBox(height: 16),
          Text(transcript.body, style: TextStyle(fontSize: 15, height: 1.6, color: colors.textPrimary)),
        ],
      ),
    );
  }
}
