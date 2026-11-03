/// Connection lifecycle for a live-transcription session, shared by the
/// speaker (TranscriptionClient) and viewer (ViewerClient) sides -- lets
/// the UI show *why* a session isn't live instead of just going silent.
enum ConnectionStatus {
  /// Initial handshake in progress.
  connecting,

  /// Streaming normally.
  connected,

  /// Lost the connection unexpectedly and is retrying with backoff.
  reconnecting,

  /// Retries exhausted; giving up until the user acts.
  connectionFailed,

  /// Viewer-only: the speaker ended the session normally (`{"type": "ended"}`).
  speakerEnded,

  /// Dropped mid-session after having connected at least once.
  networkLost,

  /// The initial connection attempt itself failed (server unreachable,
  /// refused, DNS failure, etc.) -- never got to `connected`.
  backendUnavailable,

  /// User-initiated stop; not an error.
  stopped,
}
