import 'dart:async';
import 'dart:math';

import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'connection_status.dart';
import 'live_transcript_parser.dart';

/// Streams mic audio to a live-transcription backend over WebSocket and
/// exposes the resulting text as two streams, plus a [ConnectionStatus]
/// stream so the UI always knows why transcription isn't flowing instead
/// of just going silent. Matches the protocol spoken by relays/*.py: raw
/// 16kHz mono PCM16 binary frames in, `{"text": "...", "partial": true}`
/// JSON messages out.
///
/// Reconnects automatically on an unexpected drop (exponential backoff,
/// capped retries) -- the mic keeps capturing throughout so recording
/// never visibly stops, but audio generated during the gap is not
/// buffered or replayed; it's genuinely lost, and [onStatus] reports
/// [ConnectionStatus.reconnecting] for the UI to say so rather than
/// pretending nothing happened.
class TranscriptionClient {
  final String wsUrl;
  final String sessionId;
  final int maxRetries;
  final Duration connectTimeout;

  TranscriptionClient({
    required this.wsUrl,
    required this.sessionId,
    this.maxRetries = 5,
    this.connectTimeout = const Duration(seconds: 8),
  });

  final AudioRecorder _recorder = AudioRecorder();
  WebSocketChannel? _channel;
  StreamSubscription<List<int>>? _audioSub;
  StreamSubscription? _socketSub;
  final _textController = StreamController<String>.broadcast();
  final _partialController = StreamController<String>.broadcast();
  final _statusController = StreamController<ConnectionStatus>.broadcast();
  final _parser = LiveTranscriptParser();

  ConnectionStatus _status = ConnectionStatus.connecting;
  String _currentPartial = '';
  bool _userStopped = false;
  int _generation = 0;
  int _retryCount = 0;

  /// Each completed utterance from the backend (not a running buffer --
  /// callers accumulate if they want the full transcript).
  Stream<String> get onText => _textController.stream;

  /// The current in-progress utterance, growing word-by-word. Clears
  /// (empty string) right before the matching final lands on [onText].
  Stream<String> get onPartial => _partialController.stream;

  /// Connection lifecycle -- drives the UI's status indicator.
  Stream<ConnectionStatus> get onStatus => _statusController.stream;
  ConnectionStatus get status => _status;

  void _setStatus(ConnectionStatus s) {
    _status = s;
    if (!_statusController.isClosed) _statusController.add(s);
  }

  Future<void> start() async {
    if (!await _recorder.hasPermission()) {
      throw StateError('Microphone permission denied');
    }
    _userStopped = false;
    _retryCount = 0;
    final myGen = ++_generation;
    await _connect(myGen, isInitial: true);

    final audioStream = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
    ));
    _audioSub = audioStream.listen((chunk) => _channel?.sink.add(chunk));
  }

  Future<void> _connect(int myGen, {required bool isInitial}) async {
    if (myGen != _generation) return; // superseded by a newer start()/retry
    _setStatus(isInitial ? ConnectionStatus.connecting : ConnectionStatus.reconnecting);
    final uri = Uri.parse(wsUrl).replace(queryParameters: {'role': 'speaker', 'session': sessionId});
    final channel = WebSocketChannel.connect(uri);
    try {
      await channel.ready.timeout(connectTimeout);
    } catch (_) {
      channel.sink.close().catchError((_) {});
      if (myGen != _generation) return;
      if (isInitial) {
        _setStatus(ConnectionStatus.backendUnavailable);
        rethrow;
      }
      await _scheduleRetry(myGen);
      return;
    }
    if (myGen != _generation) {
      channel.sink.close().catchError((_) {});
      return;
    }
    await _socketSub?.cancel();
    _channel = channel;
    _retryCount = 0;
    _setStatus(ConnectionStatus.connected);
    _socketSub = channel.stream.listen(
      _onMessage,
      onDone: () => _onSocketGone(myGen),
      onError: (_) => _onSocketGone(myGen),
    );
  }

  void _onMessage(dynamic message) {
    if (message is! String) return;
    _parser.parse(
      message,
      onFinal: (text) {
        _currentPartial = '';
        if (!_textController.isClosed) _textController.add(text);
      },
      onPartial: (text) {
        _currentPartial = text;
        if (!_partialController.isClosed) _partialController.add(text);
      },
      onEnded: () {}, // the relay never sends "ended" back to the speaker itself
    );
  }

  void _onSocketGone(int myGen) {
    if (_userStopped || myGen != _generation) return;
    _setStatus(ConnectionStatus.networkLost);
    _scheduleRetry(myGen);
  }

  Future<void> _scheduleRetry(int myGen) async {
    if (_userStopped || myGen != _generation) return;
    if (_retryCount >= maxRetries) {
      _setStatus(ConnectionStatus.connectionFailed);
      return;
    }
    _retryCount++;
    _setStatus(ConnectionStatus.reconnecting);
    final delayMs = min(500 * pow(2, _retryCount - 1).toInt(), 10000);
    await Future.delayed(Duration(milliseconds: delayMs));
    if (_userStopped || myGen != _generation) return;
    await _connect(myGen, isInitial: false);
  }

  /// Manually retry after retries were exhausted ([ConnectionStatus.connectionFailed]).
  Future<void> retry() async {
    if (_status != ConnectionStatus.connectionFailed) return;
    _retryCount = 0;
    await _connect(_generation, isInitial: false);
  }

  Future<void> stop() async {
    _userStopped = true;
    _generation++; // invalidate any in-flight retry/connect attempt
    await _audioSub?.cancel();
    _audioSub = null;
    if (await _recorder.isRecording()) await _recorder.stop();
    // Grace period: only if an utterance is genuinely mid-flight. Closing
    // instantly would race the relay's pause-triggered flush and lose the
    // speaker's own last sentence (it still reaches viewers via broadcast,
    // just not the speaker's own saved transcript).
    if (_channel != null && _currentPartial.isNotEmpty) {
      final gotFinal = Completer<void>();
      final sub = _textController.stream.listen((_) {
        if (!gotFinal.isCompleted) gotFinal.complete();
      });
      await Future.any([gotFinal.future, Future.delayed(const Duration(seconds: 2))]);
      await sub.cancel();
    }
    await _socketSub?.cancel();
    await _channel?.sink.close();
    _channel = null;
    _setStatus(ConnectionStatus.stopped);
  }

  void dispose() {
    stop();
    _recorder.dispose();
    _textController.close();
    _partialController.close();
    _statusController.close();
  }
}
