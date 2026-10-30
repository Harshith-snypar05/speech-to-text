import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

/// Read-only connection to a live-transcription session: no mic, no audio,
/// just the same text messages the speaker is receiving (including partial
/// word-by-word growth, same semantics as TranscriptionClient), plus an
/// "ended" signal the moment the speaker disconnects.
class ViewerClient {
  final String wsUrl;
  final String sessionId;
  ViewerClient({required this.wsUrl, required this.sessionId});

  WebSocketChannel? _channel;
  final _textController = StreamController<String>.broadcast();
  final _partialController = StreamController<String>.broadcast();
  final _endedController = StreamController<void>.broadcast();
  final List<String> _partialWords = [];

  Stream<String> get onText => _textController.stream;
  Stream<String> get onPartial => _partialController.stream;
  Stream<void> get onEnded => _endedController.stream;

  void connect() {
    final uri = Uri.parse(wsUrl).replace(queryParameters: {'role': 'viewer', 'session': sessionId});
    _channel = WebSocketChannel.connect(uri);
    _channel!.stream.listen(
      (message) {
        try {
          final data = jsonDecode(message as String) as Map<String, dynamic>;
          if (data['type'] == 'ended') {
            _endedController.add(null);
            return;
          }
          final text = (data['text'] as String?)?.trim();
          if (text == null || text.isEmpty) return;
          if (data['partial'] == true) {
            _partialWords.add(text);
            _partialController.add(_partialWords.join(' '));
          } else {
            _partialWords.clear();
            _partialController.add('');
            _textController.add(text);
          }
        } catch (_) {
          // non-JSON or malformed message; ignore
        }
      },
      onDone: () => _endedController.add(null),
      onError: (_) => _endedController.add(null),
    );
  }

  void dispose() {
    _channel?.sink.close();
    _textController.close();
    _partialController.close();
    _endedController.close();
  }
}
