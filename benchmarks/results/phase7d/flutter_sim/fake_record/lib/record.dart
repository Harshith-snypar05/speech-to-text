import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

enum AudioEncoder { pcm16bits }
class InputDevice { final String id; final String label; InputDevice({required this.id, this.label = ''}); }
class RecordConfig {
  final AudioEncoder encoder; final int sampleRate; final int numChannels; final InputDevice? device;
  const RecordConfig({this.encoder = AudioEncoder.pcm16bits, this.sampleRate = 16000, this.numChannels = 1, this.device});
}
/// Fake mic: streams a raw PCM16 file in real time, 100 ms chunks. Not the code under test.
class AudioRecorder {
  static String pcmPath = '';
  late final String _path = pcmPath;
  static int sentBytes = 0;
  bool _rec = false;
  Future<bool> hasPermission() async => true;
  Future<List<InputDevice>> listInputDevices() async => [];
  Future<bool> isRecording() async => _rec;
  Future<Stream<Uint8List>> startStream(RecordConfig c) async {
    final data = File(_path).readAsBytesSync();
    final ctl = StreamController<Uint8List>();
    _rec = true;
    () async {
      final sw = Stopwatch()..start();
      for (var off = 0, n = 0; _rec; off += 3200, n++) {
        // like a live mic: after the file ends keep streaming silence
        final inFile = off < data.length;
        final end = off + 3200 > data.length ? data.length : off + 3200;
        final chunk = inFile ? Uint8List.sublistView(data, off, end) : Uint8List(3200);
        ctl.add(chunk);
        if (inFile) sentBytes += end - off;
        final wait = (n + 1) * 100 - sw.elapsedMilliseconds;
        if (wait > 0) await Future.delayed(Duration(milliseconds: wait));
      }
    }();
    return ctl.stream;
  }
  Future<void> stop() async { _rec = false; }
  Future<void> dispose() async { _rec = false; }
}
