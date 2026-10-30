import 'package:flutter/material.dart';
import '../models/transcript.dart';
import '../theme.dart';

class TranscriptDetailScreen extends StatelessWidget {
  final Transcript transcript;
  const TranscriptDetailScreen({super.key, required this.transcript});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const BackButton(color: AppColors.textPrimary),
        title: Text(transcript.title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
        actions: [IconButton(icon: const Icon(Icons.more_horiz, color: AppColors.textPrimary), onPressed: () {})],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(transcript.dateLabel, style: const TextStyle(color: AppColors.textSecondary, fontSize: 13)),
          const SizedBox(height: 16),
          Text(transcript.body, style: const TextStyle(fontSize: 15, height: 1.6, color: AppColors.textPrimary)),
        ],
      ),
    );
  }
}
