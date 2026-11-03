import 'package:flutter_test/flutter_test.dart';
import 'package:st_transcribe/models/transcript.dart';

void main() {
  group('titleFromBody', () {
    test('takes the first 6 words of the first line', () {
      expect(titleFromBody('one two three four five six seven eight'), 'one two three four five six...');
    });

    test('short body is returned as-is, no ellipsis', () {
      expect(titleFromBody('short text'), 'short text');
    });

    test('empty body yields the placeholder title', () {
      expect(titleFromBody(''), 'Untitled transcript');
      expect(titleFromBody('   '), 'Untitled transcript');
    });

    test('only the first line is considered', () {
      expect(titleFromBody('first line\nsecond line here'), 'first line');
    });
  });

  group('previewFromBody', () {
    test('newlines collapse to spaces', () {
      expect(previewFromBody('line one\nline two'), 'line one line two');
    });

    test('truncates with ellipsis past 60 characters', () {
      final long = 'a' * 100;
      final preview = previewFromBody(long);
      expect(preview.length, 63); // 60 chars + '...'
      expect(preview.endsWith('...'), isTrue);
    });

    test('short body has no ellipsis', () {
      expect(previewFromBody('short'), 'short');
    });
  });

  group('formatDateLabel', () {
    test('formats as "Mon D, YYYY"', () {
      expect(formatDateLabel(DateTime(2026, 11, 3)), 'Nov 3, 2026');
      expect(formatDateLabel(DateTime(2026, 1, 15)), 'Jan 15, 2026');
    });
  });

  group('Transcript / TranscriptMeta', () {
    test('Transcript.meta derives title/preview/date consistently with the standalone helpers', () {
      final date = DateTime(2026, 11, 3);
      final t = Transcript(id: 'abc123', body: 'hello world this is a test', date: date);
      final meta = t.meta;
      expect(meta.id, 'abc123');
      expect(meta.title, titleFromBody(t.body));
      expect(meta.preview, previewFromBody(t.body));
      expect(meta.date, date);
    });

    test('TranscriptMeta round-trips through JSON', () {
      final meta = TranscriptMeta(id: 'id1', title: 'Title', preview: 'Preview text', date: DateTime(2026, 5, 1));
      final restored = TranscriptMeta.fromJson(meta.toJson());
      expect(restored.id, meta.id);
      expect(restored.title, meta.title);
      expect(restored.preview, meta.preview);
      expect(restored.date, meta.date);
    });
  });
}
