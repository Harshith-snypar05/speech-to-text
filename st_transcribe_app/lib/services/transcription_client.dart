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
  final String? micDeviceId;
  final String? accessCode;
  final String? authToken;
  final int maxRetries;
  final Duration connectTimeout;

  TranscriptionClient({
    required this.wsUrl,
    required this.sessionId,
    this.micDeviceId,
    this.accessCode,
    this.authToken,
    this.maxRetries = 5,
    this.connectTimeout = const Duration(seconds: 8),
  });

  final AudioRecorder _recorder = AudioRecorder();
  WebSocketChannel? _channel;
  StreamSubscription<List<int>>? _audioSub;
  StreamSubscription? _socketSub;
  final _textController = StreamController<String>.broadcast();
  final _partialController = StreamController<String>.broadcast();
  final _refineController = StreamController<({String original, String refined})>.broadcast();
  final _statusController = StreamController<ConnectionStatus>.broadcast();
  final _levelController = StreamController<double>.broadcast();
  final _parser = LiveTranscriptParser();

  ConnectionStatus _status = ConnectionStatus.connecting;
  String _currentPartial = '';
  bool _userStopped = false;
  int _generation = 0;
  int _retryCount = 0;

  /// Each completed utterance from the backend (not a running buffer --
  /// callers accumulate if they want the full transcript).
  Stream<String> get onText => _textController.stream;

  /// A refined version of an already delivered line (match it by [original]); lines are never added or removed by it.
  Stream<({String original, String refined})> get onRefine => _refineController.stream;

  /// The current in-progress utterance, growing word-by-word. Clears
  /// (empty string) right before the matching final lands on [onText].
  Stream<String> get onPartial => _partialController.stream;

  /// Real microphone level, 0..1 (RMS of each captured PCM16 chunk). Drives the waveform; never synthetic.
  Stream<double> get onLevel => _levelController.stream;

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

    InputDevice? device;
    if (micDeviceId != null) {
      final devices = await _recorder.listInputDevices().catchError((_) => <InputDevice>[]);
      for (final d in devices) {
        if (d.id == micDeviceId) {
          device = d;
          break;
        }
      }
      // If the saved device id isn't found (unplugged, permissions
      // changed), device stays null and the platform default is used --
      // silently falling back rather than failing the whole session.
    }

    final audioStream = await _recorder.startStream(RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
      device: device,
    ));
    _audioSub = audioStream.listen((chunk) {
      _channel?.sink.add(chunk);
      if (!_levelController.isClosed) _levelController.add(pcm16Rms(chunk));
    });
  }

  Future<void> _connect(int myGen, {required bool isInitial}) async {
    if (myGen != _generation) return; // superseded by a newer start()/retry
    _setStatus(isInitial ? ConnectionStatus.connecting : ConnectionStatus.reconnecting);
    final uri = Uri.parse(wsUrl).replace(queryParameters: {
      'role': 'speaker',
      'session': sessionId,
      if (accessCode != null) 'code': accessCode,
      if (authToken != null) 'token': authToken!,
    });
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
      onRefine: (original, refined) {
        if (!_refineController.isClosed) _refineController.add((original: original, refined: refined));
      },
      onPartial: (text) {
        _currentPartial = text;
        if (!_partialController.isClosed) _partialController.add(text);
      },
      onEnded: () {}, // the relay never sends "ended" back to the speaker itself
    );
  }

  /// Reason text of the last relay close (e.g. `quota_exhausted`, `allowance_reserved`, `payment_required`).
  String? closeReason;

  void _onSocketGone(int myGen) {
    if (_userStopped || myGen != _generation) return;
    final closeCode = _channel?.closeCode;
    closeReason = _channel?.closeReason;
    if (closeCode == 4402) {
      _setStatus(ConnectionStatus.outOfMinutes);
      return;
    }
    if (closeCode == 4403) {
      _setStatus(ConnectionStatus.emailNotVerified);
      return;
    }
    if (closeCode == 4409) {
      _setStatus(ConnectionStatus.superseded);
      return;
    }
    if (closeCode == 4400 || closeCode == 4401) {
      // Server rejected the connection outright (bad access code /
      // malformed params) -- retrying with the same credentials would
      // just fail again, so this is terminal, not a network blip.
      _setStatus(ConnectionStatus.unauthorized);
      return;
    }
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
    _refineController.close();
    _statusController.close();
    _levelController.close();
  }
}

/// RMS of little-endian PCM16 samples, normalised to 0..1 (0 for empty input).
double pcm16Rms(List<int> bytes) {
  final n = bytes.length ~/ 2;
  if (n == 0) return 0;
  double acc = 0;
  for (var i = 0; i < n; i++) {
    var v = bytes[2 * i] | (bytes[2 * i + 1] << 8);
    if (v >= 0x8000) v -= 0x10000;
    acc += v * v;
  }
  return (sqrt(acc / n) / 32768.0).clamp(0.0, 1.0);
}
