/// Backend under test. Now pointed at the faster-whisper relay (word-by-word
/// partial streaming + clean final commits). whisper.cpp (8765) and
/// openai/whisper (8766) relays are still running untouched, just not what
/// the app is pointed at right now.
///
/// Currently pointed at a Cloudflare quick tunnel so remote viewers can
/// actually use transcription, not just localhost. Random URL, dies when
/// the tunnel process stops -- update this when it rotates.
const String kTranscriptionBackendUrl = 'ws://localhost:8767';
