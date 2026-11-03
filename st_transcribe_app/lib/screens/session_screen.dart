import 'package:flutter/material.dart';
import '../config.dart';
import '../services/connection_status.dart';
import '../services/session_id.dart';
import '../services/transcription_client.dart';
import '../services/transcript_storage.dart';
import '../theme.dart';
import '../widgets/st_logo.dart';
import '../widgets/share_link_sheet.dart';

class SessionScreen extends StatefulWidget {
  const SessionScreen({super.key});

  @override
  State<SessionScreen> createState() => _SessionScreenState();
}

class _SessionScreenState extends State<SessionScreen> with SingleTickerProviderStateMixin {
  bool _recording = false;
  bool _connecting = false;
  String? _error;
  ConnectionStatus _connStatus = ConnectionStatus.stopped;
  final List<String> _utterances = [];
  String _currentPartial = '';
  TranscriptionClient? _client;
  late final AnimationController _pulse;
  late final String _sessionId;

  @override
  void initState() {
    super.initState();
    _sessionId = generateSessionId();
    _pulse = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat();
  }

  @override
  void dispose() {
    _pulse.dispose();
    _client?.dispose();
    super.dispose();
  }

  String get _transcript => _utterances.join(' ');

  Future<void> _toggle() async {
    if (_recording) {
      await _stop();
    } else {
      await _start();
    }
  }

  Future<void> _start() async {
    setState(() {
      _connecting = true;
      _error = null;
      _utterances.clear();
      _currentPartial = '';
    });
    final client = TranscriptionClient(wsUrl: kTranscriptionBackendUrl, sessionId: _sessionId);
    client.onText.listen((text) {
      if (mounted) setState(() => _utterances.add(text));
    });
    client.onPartial.listen((text) {
      if (mounted) setState(() => _currentPartial = text);
    });
    client.onStatus.listen((status) {
      if (!mounted) return;
      setState(() {
        _connStatus = status;
        if (status == ConnectionStatus.connected) _error = null;
      });
    });
    try {
      await client.start();
      setState(() {
        _client = client;
        _recording = true;
        _connecting = false;
      });
    } catch (e) {
      setState(() {
        _error = client.status == ConnectionStatus.backendUnavailable
            ? 'Could not reach the transcription server. Check your connection and try again.'
            : 'Could not start: $e';
        _connecting = false;
      });
      client.dispose();
    }
  }

  void _retryConnection() => _client?.retry();

  Future<void> _stop() async {
    await _client?.stop();
    final saved = await TranscriptStorage.save(_transcript);
    setState(() {
      _recording = false;
      _client = null;
      _currentPartial = '';
      _connStatus = ConnectionStatus.stopped;
    });
    if (mounted && saved != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Transcript saved: ${saved.title}')),
      );
    }
  }

  /// Stops the live session (ends the broadcast for any viewers, saves the
  /// transcript) and returns to Home, which refreshes Recent Transcripts.
  Future<void> _endSession() async {
    await _stop();
    if (mounted) Navigator.of(context).pop();
  }

  void _openShareSheet() {
    // Uri.base.origin reflects wherever this web build is actually being
    // served from (localhost, a Cloudflare tunnel, a real domain later) --
    // real, not a placeholder. On native mobile builds there's no "current
    // URL" to derive this from; that needs a configured viewer-site host
    // instead, not handled yet.
    final link = '${Uri.base.origin}/#/viewer?session=$_sessionId';
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => ShareLinkSheet(link: link),
    );
  }

  @override
  Widget build(BuildContext context) {
    final color = _recording ? AppColors.recordRed : AppColors.primaryBlue;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            SizedBox(
              height: 90,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.settings_outlined, color: AppColors.textPrimary),
                          onPressed: () => Navigator.of(context).pushNamed('/settings'),
                        ),
                        Stack(
                          clipBehavior: Clip.none,
                          children: [
                            IconButton(
                              icon: const Icon(Icons.ios_share, color: AppColors.textPrimary),
                              onPressed: _openShareSheet,
                            ),
                            Positioned(
                              right: 6,
                              top: 6,
                              child: Container(
                                width: 9,
                                height: 9,
                                decoration: BoxDecoration(
                                  color: _recording ? AppColors.liveGreen : const Color(0xFFFFC107),
                                  shape: BoxShape.circle,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const IgnorePointer(child: StLogo(size: 72)),
                ],
              ),
            ),
            const SizedBox(height: 32),
            GestureDetector(
              onTap: _connecting ? null : _toggle,
              child: AnimatedBuilder(
                animation: _pulse,
                builder: (context, _) {
                  return SizedBox(
                    width: 180,
                    height: 180,
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        _ring(color, 180, 0.12),
                        _ring(color, 140 + 20 * _pulse.value, 0.18),
                        Container(
                          width: 100,
                          height: 100,
                          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                          child: _connecting
                              ? const Padding(
                                  padding: EdgeInsets.all(28),
                                  child: CircularProgressIndicator(color: Colors.white, strokeWidth: 3),
                                )
                              : const Icon(Icons.mic, color: Colors.white, size: 40),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
            Text(
              _connecting ? 'Connecting...' : (_recording ? 'Tap to stop' : 'Tap to start'),
              style: const TextStyle(color: AppColors.textSecondary, fontSize: 14),
            ),
            if (_recording) ...[
              const SizedBox(height: 12),
              TextButton.icon(
                onPressed: _endSession,
                icon: const Icon(Icons.stop_circle_outlined, color: AppColors.recordRed, size: 18),
                label: const Text('End Session', style: TextStyle(color: AppColors.recordRed, fontWeight: FontWeight.w700)),
              ),
            ],
            if (_recording && _connStatus != ConnectionStatus.connected) ...[
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  children: [
                    Text(
                      _statusMessage(_connStatus),
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: AppColors.recordRed, fontSize: 13),
                    ),
                    if (_connStatus == ConnectionStatus.connectionFailed) ...[
                      const SizedBox(height: 4),
                      TextButton(
                        onPressed: _retryConnection,
                        child: const Text('Retry', style: TextStyle(color: AppColors.primaryBlue, fontWeight: FontWeight.w700)),
                      ),
                    ],
                  ],
                ),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Text(_error!,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: AppColors.recordRed, fontSize: 13)),
              ),
            ],
            const SizedBox(height: 16),
            Expanded(
              child: _TranscriptionSheet(
                recording: _recording,
                transcript: _transcript,
                currentPartial: _currentPartial,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _statusMessage(ConnectionStatus status) {
    switch (status) {
      case ConnectionStatus.networkLost:
        return 'Connection lost. Anything said right now won\'t be transcribed.';
      case ConnectionStatus.reconnecting:
        return 'Reconnecting...';
      case ConnectionStatus.connectionFailed:
        return 'Connection failed. Recording has stopped transcribing.';
      case ConnectionStatus.backendUnavailable:
        return 'Transcription server unavailable.';
      default:
        return '';
    }
  }

  Widget _ring(Color color, double size, double opacity) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(shape: BoxShape.circle, color: color.withValues(alpha: opacity)),
    );
  }
}

class _TranscriptionSheet extends StatelessWidget {
  final bool recording;
  final String transcript;
  final String currentPartial;
  const _TranscriptionSheet({required this.recording, required this.transcript, required this.currentPartial});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        boxShadow: [BoxShadow(color: Color(0x14000000), blurRadius: 16, offset: Offset(0, -4))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              margin: const EdgeInsets.only(bottom: 16),
              decoration: BoxDecoration(color: AppColors.cardBorder, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Transcription', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
              Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(color: AppColors.primaryBlue, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 6),
                  Text(recording ? 'Live' : 'Ready',
                      style: const TextStyle(color: AppColors.textSecondary, fontSize: 13, fontWeight: FontWeight.w600)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 20),
          if (transcript.isEmpty && currentPartial.isEmpty)
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      decoration: const BoxDecoration(color: AppColors.lightBlueBg, shape: BoxShape.circle),
                      child: const Icon(Icons.graphic_eq, color: AppColors.primaryBlue),
                    ),
                    const SizedBox(height: 16),
                    const Text('Start speaking...', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                    const SizedBox(height: 6),
                    const Text('Your words will appear here in real time.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
                  ],
                ),
              ),
            )
          else
            Expanded(
              child: SingleChildScrollView(
                child: Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: transcript,
                        style: const TextStyle(fontSize: 15, height: 1.5, color: AppColors.textPrimary),
                      ),
                      if (currentPartial.isNotEmpty)
                        TextSpan(
                          text: '${transcript.isEmpty ? '' : ' '}$currentPartial',
                          style: const TextStyle(fontSize: 15, height: 1.5, color: AppColors.textSecondary),
                        ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
