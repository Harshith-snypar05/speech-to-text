import 'package:flutter_test/flutter_test.dart';
import 'package:st_transcribe/services/live_transcript_parser.dart';

void main() {
  late LiveTranscriptParser parser;
  late List<String> finals;
  late List<String> partials;
  late int endedCount;

  void parse(String raw) {
    parser.parse(
      raw,
      onFinal: finals.add,
      onPartial: partials.add,
      onEnded: () => endedCount++,
    );
  }

  setUp(() {
    parser = LiveTranscriptParser();
    finals = [];
    partials = [];
    endedCount = 0;
  });

  test('final message with partial:false triggers onFinal and clears partial', () {
    parse('{"text": "hello world", "partial": false}');
    expect(finals, ['hello world']);
    expect(partials, ['']); // partial is cleared right before the final fires
  });

  test('final message with no partial key defaults to final (defensive -- the relay always sends it explicitly now)', () {
    parse('{"text": "hello world"}');
    expect(finals, ['hello world']);
  });

  test('partial messages accumulate word-by-word, not replace', () {
    parse('{"text": "hello", "partial": true}');
    parse('{"text": "world", "partial": true}');
    expect(partials, ['hello', 'hello world']);
    expect(finals, isEmpty);
  });

  test('final after partials resets the partial accumulator for the next utterance', () {
    parse('{"text": "hello", "partial": true}');
    parse('{"text": "world", "partial": true}');
    parse('{"text": "hello world", "partial": false}');
    parse('{"text": "next", "partial": true}');
    expect(partials.last, 'next'); // not "hello worldnext" or similar leakage
  });

  test('ended message triggers onEnded, not onFinal/onPartial', () {
    parse('{"type": "ended"}');
    expect(endedCount, 1);
    expect(finals, isEmpty);
    expect(partials, isEmpty);
  });

  test('empty text is ignored', () {
    parse('{"text": "", "partial": true}');
    parse('{"text": "   ", "partial": false}');
    expect(finals, isEmpty);
    expect(partials, isEmpty);
  });

  test('malformed JSON is silently ignored, not thrown', () {
    expect(() => parse('not json at all'), returnsNormally);
    expect(finals, isEmpty);
    expect(partials, isEmpty);
  });

  test('message missing text field is ignored', () {
    parse('{"foo": "bar"}');
    expect(finals, isEmpty);
    expect(partials, isEmpty);
  });

  test('text is trimmed', () {
    parse('{"text": "  hello  ", "partial": false}');
    expect(finals, ['hello']);
  });
}
