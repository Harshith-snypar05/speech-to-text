import 'dart:async';
import 'dart:math';

import 'package:web_socket_channel/web_socket_channel.dart';

import 'connection_status.dart';
import 'live_transcript_parser.dart';

/// Read-only connection to a live-transcription session: no mic, no audio,
/// just the same text messages the speaker is receiving (including partial
/// word-by-word growth, same semantics as TranscriptionClient), plus a
/// [ConnectionStatus] stream distinguishing "the speaker ended the session"
/// from "we lost the connection and are retrying."
///
/// Reconnects automatically on an unexpected drop (exponential backoff,
/// capped retries). A clean `{"type": "ended"}` from the speaker is treated
/// as final -- no reconnect attempt, the session is genuinely over.
class ViewerClient {
  final String wsUrl;
  final String sessionId;
  final int maxRetries;
  final Duration connectTimeout;

  ViewerClient({
    required this.wsUrl,
    required this.sessionId,
    this.maxRetries = 5,
    this.connectTimeout = const Duration(seconds: 8),
  });

  WebSocketChannel? _channel;
  StreamSubscription? _socketSub;
  final _textController = StreamController<String>.broadcast();
  final _partialController = StreamController<String>.broadcast();
  final _statusController = StreamController<ConnectionStatus>.broadcast();
  final _parser = LiveTranscriptParser();

  ConnectionStatus _status = ConnectionStatus.connecting;
  bool _stopped = false;
  bool _ended = false;
  int _generation = 0;
  int _retryCount = 0;

  Stream<String> get onText => _textController.stream;
  Stream<String> get onPartial => _partialController.stream;
  Stream<ConnectionStatus> get onStatus => _statusController.stream;
  ConnectionStatus get status => _status;

  void _setStatus(ConnectionStatus s) {
    _status = s;
    if (!_statusController.isClosed) _statusController.add(s);
  }

  void connect() {
    _stopped = false;
    _retryCount = 0;
    final myGen = ++_generation;
    _connect(myGen, isInitial: true);
  }

  Future<void> _connect(int myGen, {required bool isInitial}) async {
    if (myGen != _generation) return;
    _setStatus(isInitial ? ConnectionStatus.connecting : ConnectionStatus.reconnecting);
    final uri = Uri.parse(wsUrl).replace(queryParameters: {'role': 'viewer', 'session': sessionId});
    final channel = WebSocketChannel.connect(uri);
    try {
      await channel.ready.timeout(connectTimeout);
    } catch (_) {
      channel.sink.close().catchError((_) {});
      if (myGen != _generation) return;
      if (isInitial) {
        _setStatus(ConnectionStatus.backendUnavailable);
        return;
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
        if (!_textController.isClosed) _textController.add(text);
      },
      onPartial: (text) {
        if (!_partialController.isClosed) _partialController.add(text);
      },
      onEnded: () {
        _ended = true;
        _setStatus(ConnectionStatus.speakerEnded);
      },
    );
  }

  void _onSocketGone(int myGen) {
    if (_stopped || _ended || myGen != _generation) return;
    _setStatus(ConnectionStatus.networkLost);
    _scheduleRetry(myGen);
  }

  Future<void> _scheduleRetry(int myGen) async {
    if (_stopped || _ended || myGen != _generation) return;
    if (_retryCount >= maxRetries) {
      _setStatus(ConnectionStatus.connectionFailed);
      return;
    }
    _retryCount++;
    _setStatus(ConnectionStatus.reconnecting);
    final delayMs = min(500 * pow(2, _retryCount - 1).toInt(), 10000);
    await Future.delayed(Duration(milliseconds: delayMs));
    if (_stopped || _ended || myGen != _generation) return;
    await _connect(myGen, isInitial: false);
  }

  /// Manually retry after retries were exhausted ([ConnectionStatus.connectionFailed]).
  Future<void> retry() async {
    if (_status != ConnectionStatus.connectionFailed) return;
    _retryCount = 0;
    await _connect(_generation, isInitial: false);
  }

  void dispose() {
    _stopped = true;
    _generation++;
    _socketSub?.cancel();
    _channel?.sink.close();
    _textController.close();
    _partialController.close();
    _statusController.close();
  }
}
