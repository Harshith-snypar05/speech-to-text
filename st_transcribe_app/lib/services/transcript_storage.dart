import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/transcript.dart';
import 'web_download_stub.dart' if (dart.library.html) 'web_download_web.dart';

/// Saves/lists transcripts. Native: real .txt files in the app's documents
/// directory, one per transcript, plus a small index.json of
/// title/preview/date so the Home screen's Recent Transcripts list doesn't
/// have to read every transcript's full body just to render previews. Web:
/// the same split, using SharedPreferences (one lightweight index key, one
/// full-body key per transcript) plus a real .txt download (browsers can't
/// write to the filesystem directly).
class TranscriptStorage {
  static const _webIndexKey = 'transcript_index';
  static const _webBodyKeyPrefix = 'transcript_body_';
  static const _legacyWebKey = 'saved_transcripts'; // pre-index format, migrated on first read

  static Future<Directory> _dir() async {
    final docs = await getApplicationDocumentsDirectory();
    final dir = Directory('${docs.path}/transcripts');
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  static File _indexFile(Directory dir) => File('${dir.path}/index.json');

  static String _newId(DateTime date) => date.toIso8601String().replaceAll(RegExp(r'[:.]'), '-');

  static Future<Transcript?> save(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return null;
    final date = DateTime.now();
    final id = _newId(date);
    final transcript = Transcript(id: id, body: trimmed, date: date);

    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('$_webBodyKeyPrefix$id', trimmed);
      final index = await _readWebIndex(prefs);
      index.insert(0, transcript.meta);
      await _writeWebIndex(prefs, index);
      triggerWebDownload('transcript_$id', trimmed);
      return transcript;
    }

    final dir = await _dir();
    await File('${dir.path}/$id.txt').writeAsString(trimmed);
    final index = await _readNativeIndex(dir);
    index.insert(0, transcript.meta);
    await _writeNativeIndex(dir, index);
    return transcript;
  }

  /// Lightweight listing: title/preview/date only, no transcript bodies
  /// read. What the Home screen uses.
  static Future<List<TranscriptMeta>> listMeta() async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      return _readWebIndex(prefs);
    }
    final dir = await _dir();
    return _readNativeIndex(dir);
  }

  /// Loads one transcript's full body by id -- only called when actually
  /// opening a transcript or exporting it, not for the list view.
  static Future<String?> loadBody(String id) async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString('$_webBodyKeyPrefix$id');
    }
    final dir = await _dir();
    final file = File('${dir.path}/$id.txt');
    if (!await file.exists()) return null;
    return file.readAsString();
  }

  static Future<Transcript?> load(TranscriptMeta meta) async {
    final body = await loadBody(meta.id);
    if (body == null) return null;
    return Transcript(id: meta.id, body: body, date: meta.date);
  }

  /// Lets the user download/export a specific transcript (e.g. from the
  /// "..." menu on a Recent Transcripts tile). Web: triggers a real file
  /// download. Native: already has a real file on disk, so hands off to the
  /// OS share sheet (includes "Save to Files") instead of duplicating it.
  static Future<void> export(TranscriptMeta meta) async {
    final body = await loadBody(meta.id);
    if (body == null) return;
    final filename = 'transcript_${meta.id}';
    if (kIsWeb) {
      triggerWebDownload(filename, body);
      return;
    }
    SharePlus.instance.share(ShareParams(text: body, subject: '$filename.txt'));
  }

  // --- native index (index.json) ---

  static Future<List<TranscriptMeta>> _readNativeIndex(Directory dir) async {
    final file = _indexFile(dir);
    if (await file.exists()) {
      try {
        final raw = jsonDecode(await file.readAsString()) as List;
        return raw.map((e) => TranscriptMeta.fromJson(e as Map<String, dynamic>)).toList();
      } catch (_) {
        // Fall through to rebuild -- a corrupted index shouldn't lose access
        // to transcripts that still exist on disk.
      }
    }
    return _rebuildNativeIndex(dir);
  }

  /// One-time migration path: builds index.json from whatever .txt files
  /// already exist (pre-index saves, or a corrupted index). Reads every
  /// file's content once to derive title/preview -- the exact cost this
  /// change avoids paying on every Home screen load, paid once here
  /// instead so existing transcripts keep working.
  static Future<List<TranscriptMeta>> _rebuildNativeIndex(Directory dir) async {
    final files = (await dir.list().toList()).whereType<File>().where((f) => f.path.endsWith('.txt')).toList();
    files.sort((a, b) => b.statSync().modified.compareTo(a.statSync().modified));
    final index = <TranscriptMeta>[];
    for (final f in files) {
      final id = f.uri.pathSegments.last.replaceAll('.txt', '');
      final body = await f.readAsString();
      index.add(TranscriptMeta.fromBody(id: id, body: body, date: f.statSync().modified));
    }
    await _writeNativeIndex(dir, index);
    return index;
  }

  static Future<void> _writeNativeIndex(Directory dir, List<TranscriptMeta> index) async {
    await _indexFile(dir).writeAsString(jsonEncode(index.map((m) => m.toJson()).toList()));
  }

  // --- web index (SharedPreferences) ---

  static Future<List<TranscriptMeta>> _readWebIndex(SharedPreferences prefs) async {
    final raw = prefs.getString(_webIndexKey);
    if (raw != null) {
      try {
        final list = jsonDecode(raw) as List;
        return list.map((e) => TranscriptMeta.fromJson(e as Map<String, dynamic>)).toList();
      } catch (_) {
        // fall through to legacy migration/empty
      }
    }
    return _migrateLegacyWebIndex(prefs);
  }

  /// One-time migration from the pre-index format (a single StringList of
  /// full `{body, date}` JSON blobs) into the index + per-id body key
  /// scheme. Runs once; the legacy key is removed after a successful
  /// migration so this doesn't re-run on every load.
  static Future<List<TranscriptMeta>> _migrateLegacyWebIndex(SharedPreferences prefs) async {
    final legacy = prefs.getStringList(_legacyWebKey);
    if (legacy == null || legacy.isEmpty) return [];
    final index = <TranscriptMeta>[];
    for (final raw in legacy) {
      try {
        final json = jsonDecode(raw) as Map<String, dynamic>;
        final date = DateTime.parse(json['date'] as String);
        final body = json['body'] as String;
        final id = _newId(date);
        await prefs.setString('$_webBodyKeyPrefix$id', body);
        index.add(TranscriptMeta.fromBody(id: id, body: body, date: date));
      } catch (_) {
        continue; // skip anything unparseable rather than losing the rest
      }
    }
    await _writeWebIndex(prefs, index);
    await prefs.remove(_legacyWebKey);
    return index;
  }

  static Future<void> _writeWebIndex(SharedPreferences prefs, List<TranscriptMeta> index) async {
    await prefs.setString(_webIndexKey, jsonEncode(index.map((m) => m.toJson()).toList()));
  }
}
