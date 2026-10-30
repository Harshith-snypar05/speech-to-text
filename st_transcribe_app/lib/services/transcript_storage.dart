import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/transcript.dart';
import 'web_download_stub.dart' if (dart.library.html) 'web_download_web.dart';

/// Saves/lists transcripts. Native: real .txt files in the app's documents
/// directory. Web: browsers can't write to the filesystem, so transcripts
/// go into browser storage (so Recent Transcripts still works) and also
/// trigger a real .txt download (so there's an actual file on the user's
/// device, same intent as the native path).
class TranscriptStorage {
  static const _webPrefsKey = 'saved_transcripts';

  static Future<Directory> _dir() async {
    final docs = await getApplicationDocumentsDirectory();
    final dir = Directory('${docs.path}/transcripts');
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  static Future<Transcript?> save(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return null;
    final transcript = Transcript(body: trimmed, date: DateTime.now());

    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      final existing = prefs.getStringList(_webPrefsKey) ?? [];
      existing.insert(0, jsonEncode(transcript.toJson()));
      await prefs.setStringList(_webPrefsKey, existing);
      triggerWebDownload('transcript_${transcript.date.toIso8601String().replaceAll(RegExp(r'[:.]'), '-')}', trimmed);
      return transcript;
    }

    final dir = await _dir();
    final stamp = transcript.date.toIso8601String().replaceAll(RegExp(r'[:.]'), '-');
    final file = File('${dir.path}/transcript_$stamp.txt');
    await file.writeAsString(trimmed);
    return transcript;
  }

  /// Lets the user download/export a specific transcript (e.g. from the
  /// "..." menu on a Recent Transcripts tile). Web: triggers a real file
  /// download. Native: already has a real file on disk, so hands off to the
  /// OS share sheet (includes "Save to Files") instead of duplicating it.
  static void export(Transcript t) {
    final filename = 'transcript_${t.date.toIso8601String().replaceAll(RegExp(r'[:.]'), '-')}';
    if (kIsWeb) {
      triggerWebDownload(filename, t.body);
      return;
    }
    SharePlus.instance.share(ShareParams(text: t.body, subject: '$filename.txt'));
  }

  static Future<List<Transcript>> list() async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      final existing = prefs.getStringList(_webPrefsKey) ?? [];
      return existing.map((e) => Transcript.fromJson(jsonDecode(e) as Map<String, dynamic>)).toList();
    }

    final dir = await _dir();
    final files = (await dir.list().toList()).whereType<File>().where((f) => f.path.endsWith('.txt')).toList();
    files.sort((a, b) => b.statSync().modified.compareTo(a.statSync().modified));
    final transcripts = <Transcript>[];
    for (final f in files) {
      transcripts.add(Transcript(body: await f.readAsString(), date: f.statSync().modified));
    }
    return transcripts;
  }
}
