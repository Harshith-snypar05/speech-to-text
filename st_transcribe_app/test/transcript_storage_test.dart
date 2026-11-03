import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:st_transcribe/services/transcript_storage.dart';

/// Points path_provider at a real temp directory instead of a platform
/// channel -- actual file I/O happens, just rooted somewhere disposable.
class _FakePathProvider extends PathProviderPlatform with MockPlatformInterfaceMixin {
  final String path;
  _FakePathProvider(this.path);

  @override
  Future<String?> getApplicationDocumentsPath() async => path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('stt_storage_test_');
    PathProviderPlatform.instance = _FakePathProvider(tempDir.path);
    SharedPreferences.setMockInitialValues({});
  });

  tearDown(() async {
    if (await tempDir.exists()) await tempDir.delete(recursive: true);
  });

  test('save() writes a .txt file and returns a Transcript with matching body', () async {
    final saved = await TranscriptStorage.save('hello world');
    expect(saved, isNotNull);
    expect(saved!.body, 'hello world');
    final file = File('${tempDir.path}/transcripts/${saved.id}.txt');
    expect(await file.exists(), isTrue);
    expect(await file.readAsString(), 'hello world');
  });

  test('save() with empty/whitespace-only text returns null and writes nothing', () async {
    final saved = await TranscriptStorage.save('   ');
    expect(saved, isNull);
    final meta = await TranscriptStorage.listMeta();
    expect(meta, isEmpty);
  });

  test('listMeta() reflects saved transcripts without needing their bodies read by the caller', () async {
    await TranscriptStorage.save('first transcript body');
    await Future.delayed(const Duration(milliseconds: 2));
    await TranscriptStorage.save('second transcript body');

    final metas = await TranscriptStorage.listMeta();
    expect(metas.length, 2);
    expect(metas.map((m) => m.title), containsAll(['first transcript body', 'second transcript body']));
  });

  test('loadBody() returns the full body for a given id, null for an unknown id', () async {
    final saved = await TranscriptStorage.save('full body content here');
    final body = await TranscriptStorage.loadBody(saved!.id);
    expect(body, 'full body content here');

    final missing = await TranscriptStorage.loadBody('does-not-exist');
    expect(missing, isNull);
  });

  test('load(meta) reconstructs a full Transcript from metadata', () async {
    final saved = await TranscriptStorage.save('reconstruct me');
    final metas = await TranscriptStorage.listMeta();
    final meta = metas.firstWhere((m) => m.id == saved!.id);

    final reloaded = await TranscriptStorage.load(meta);
    expect(reloaded, isNotNull);
    expect(reloaded!.body, 'reconstruct me');
    expect(reloaded.id, saved!.id);
  });

  test('index.json is rebuilt automatically from existing .txt files if missing (pre-upgrade data)', () async {
    // Simulate data saved by a version of the app before index.json existed:
    // a .txt file with no corresponding index entry.
    final dir = Directory('${tempDir.path}/transcripts');
    await dir.create(recursive: true);
    await File('${dir.path}/2026-01-01T00-00-00-000.txt').writeAsString('pre-upgrade transcript');

    final metas = await TranscriptStorage.listMeta();
    expect(metas.length, 1);
    expect(metas.first.title, 'pre-upgrade transcript');

    // And the index should now exist so the next read doesn't re-scan.
    expect(await File('${dir.path}/index.json').exists(), isTrue);
  });

  test('a corrupted index.json falls back to rebuilding from the .txt files', () async {
    final dir = Directory('${tempDir.path}/transcripts');
    await dir.create(recursive: true);
    await File('${dir.path}/2026-01-01T00-00-00-000.txt').writeAsString('recoverable transcript');
    await File('${dir.path}/index.json').writeAsString('{not valid json');

    final metas = await TranscriptStorage.listMeta();
    expect(metas.length, 1);
    expect(metas.first.title, 'recoverable transcript');
  });
}
