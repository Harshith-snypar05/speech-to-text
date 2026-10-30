import 'dart:async';
import 'dart:convert';

import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// Streams mic audio to a live-transcription backend over WebSocket and
/// exposes the resulting text as two streams. Matches the protocol spoken
/// by relays/*.py: raw 16kHz mono PCM16 binary frames in,
/// `{"text": "...", "partial": true}` JSON messages out. Relays that don't
/// send `partial` (whisper.cpp, openai/whisper) implicitly mean "final" --
/// `partial` defaults to false, so those still work unchanged on [onText].
class TranscriptionClient {
  final String wsUrl;
  final String sessionId;
  TranscriptionClient({required this.wsUrl, required this.sessionId});

  final AudioRecorder _recorder = AudioRecorder();
  WebSocketChannel? _channel;
  StreamSubscription<List<int>>? _audioSub;
  final _textController = StreamController<String>.broadcast();
  final _partialController = StreamController<String>.broadcast();
  final List<String> _partialWords = [];

  /// Each completed utterance from the backend (not a running buffer --
  /// callers accumulate if they want the full transcript).
  Stream<String> get onText => _textController.stream;

  /// The current in-progress utterance, growing word-by-word as the backend
  /// streams partials. Emits the full current line each time (not deltas) --
  /// callers just display whatever comes out. Clears (empty string) right
  /// before the matching final lands on [onText].
  Stream<String> get onPartial => _partialController.stream;

  Future<void> start() async {
    if (!await _recorder.hasPermission()) {
      throw StateError('Microphone permission denied');
    }

    final uri = Uri.parse(wsUrl).replace(queryParameters: {'role': 'speaker', 'session': sessionId});
    _channel = WebSocketChannel.connect(uri);
    _channel!.stream.listen(
      (message) {
        try {
          final data = jsonDecode(message as String) as Map<String, dynamic>;
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
      onError: (_) {},
    );

    final audioStream = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
    ));
    _audioSub = audioStream.listen((chunk) => _channel?.sink.add(chunk));
  }

  Future<void> stop() async {
    await _audioSub?.cancel();
    _audioSub = null;
    if (await _recorder.isRecording()) await _recorder.stop();
    await _channel?.sink.close();
    _channel = null;
  }

  void dispose() {
    stop();
    _recorder.dispose();
    _textController.close();
    _partialController.close();
  }
}
