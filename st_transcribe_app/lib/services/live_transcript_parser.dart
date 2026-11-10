import 'dart:convert';

/// Parses the relay wire protocol (`{"text": ..., "partial": bool}` /
/// `{"type": "ended"}`) into callbacks. Identical logic was previously
/// duplicated between TranscriptionClient and ViewerClient.
class LiveTranscriptParser {
  final List<String> _partialWords = [];

  void parse(
    String raw, {
    required void Function(String text) onFinal,
    required void Function(String text) onPartial,
    required void Function() onEnded,
    void Function(String original, String refined)? onRefine,
  }) {
    Map<String, dynamic> data;
    try {
      data = jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return; // non-JSON or malformed message; ignore
    }
    if (data['type'] == 'ended') {
      onEnded();
      return;
    }
    if (data['type'] == 'refine') {
      // A later, better version of a line already delivered as a final. Never touches the live partial.
      final original = data['original'];
      final refined = data['refined'];
      if (onRefine != null && original is String && refined is String && refined.trim().isNotEmpty) {
        onRefine(original, refined.trim());
      }
      return;
    }
    final text = (data['text'] as String?)?.trim();
    if (text == null || text.isEmpty) return;
    if (data['partial'] == true) {
      _partialWords.add(text);
      onPartial(_partialWords.join(' '));
    } else {
      _partialWords.clear();
      onPartial('');
      onFinal(text);
    }
  }
}
