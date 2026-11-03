import 'package:flutter_test/flutter_test.dart';
import 'package:st_transcribe/services/connection_status.dart';

void main() {
  test('every status the clients can emit is a distinct enum value', () {
    // Regression guard: TranscriptionClient/ViewerClient map specific
    // scenarios (auth rejection, network drop, backend unreachable, clean
    // speaker-ended) onto distinct statuses so the UI can tell them apart.
    // A naive merge of two of these during a refactor would silently
    // collapse two different user-facing messages into one.
    expect(ConnectionStatus.values.toSet().length, ConnectionStatus.values.length);
    expect(ConnectionStatus.values, containsAll([
      ConnectionStatus.connecting,
      ConnectionStatus.connected,
      ConnectionStatus.reconnecting,
      ConnectionStatus.connectionFailed,
      ConnectionStatus.speakerEnded,
      ConnectionStatus.networkLost,
      ConnectionStatus.backendUnavailable,
      ConnectionStatus.unauthorized,
      ConnectionStatus.stopped,
    ]));
  });
}
