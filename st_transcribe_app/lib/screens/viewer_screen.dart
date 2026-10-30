import 'package:flutter/material.dart';
import '../config.dart';
import '../services/viewer_client.dart';
import '../theme.dart';
import '../widgets/st_logo.dart';

enum _ViewerState { connecting, live, ended, invalid }

/// Viewer-side experience for someone who opened a shared live-transcript
/// link (`?session=<id>`). Connects read-only to the same backend relay the
/// speaker is streaming to; the session ends the moment the speaker stops.
class ViewerScreen extends StatefulWidget {
  final String? sessionId;
  const ViewerScreen({super.key, required this.sessionId});

  @override
  State<ViewerScreen> createState() => _ViewerScreenState();
}

class _ViewerScreenState extends State<ViewerScreen> {
  _ViewerState _state = _ViewerState.connecting;
  final List<String> _utterances = [];
  String _currentPartial = '';
  ViewerClient? _client;

  String get _transcript => _utterances.join(' ');

  @override
  void initState() {
    super.initState();
    final sessionId = widget.sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      _state = _ViewerState.invalid;
      return;
    }
    final client = ViewerClient(wsUrl: kTranscriptionBackendUrl, sessionId: sessionId);
    client.onText.listen((text) {
      if (!mounted) return;
      setState(() {
        _utterances.add(text);
        _state = _ViewerState.live;
      });
    });
    client.onPartial.listen((text) {
      if (!mounted) return;
      setState(() {
        _currentPartial = text;
        _state = _ViewerState.live;
      });
    });
    client.onEnded.listen((_) {
      if (mounted) setState(() => _state = _ViewerState.ended);
    });
    client.connect();
    _client = client;
  }

  @override
  void dispose() {
    _client?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: switch (_state) {
          _ViewerState.invalid => const _MessageView(
              status: 'Invalid link', message: 'This link is missing a session id.', dotColor: AppColors.idleGrayDot),
          _ViewerState.connecting => const _ConnectingView(),
          _ViewerState.live => _LiveView(transcript: _transcript, currentPartial: _currentPartial),
          _ViewerState.ended => _EndedView(transcript: _transcript),
        },
      ),
    );
  }
}

Widget _topBar({required Widget statusWidget}) {
  return Padding(
    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
    child: Row(
      children: [
        const StLogo(size: 26),
        const SizedBox(width: 8),
        statusWidget,
        const Spacer(),
        const Icon(Icons.more_horiz, color: AppColors.textPrimary),
      ],
    ),
  );
}

class _ConnectingView extends StatelessWidget {
  const _ConnectingView();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _topBar(statusWidget: const SizedBox.shrink()),
        const Expanded(
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(color: AppColors.primaryBlue),
                SizedBox(height: 20),
                Text('Connecting...', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                SizedBox(height: 6),
                Text('Please wait while we join the live session.',
                    style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _MessageView extends StatelessWidget {
  final String status;
  final String message;
  final Color dotColor;
  const _MessageView({required this.status, required this.message, required this.dotColor});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _topBar(
          statusWidget: Row(
            children: [
              Icon(Icons.circle, size: 8, color: dotColor),
              const SizedBox(width: 6),
              Text(status, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
            ],
          ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Text(message, style: const TextStyle(fontSize: 16, height: 1.6, color: AppColors.textSecondary)),
          ),
        ),
      ],
    );
  }
}

class _LiveView extends StatelessWidget {
  final String transcript;
  final String currentPartial;
  const _LiveView({required this.transcript, required this.currentPartial});

  @override
  Widget build(BuildContext context) {
    final isEmpty = transcript.isEmpty && currentPartial.isEmpty;
    return Column(
      children: [
        _topBar(
          statusWidget: const Row(
            children: [
              Icon(Icons.circle, size: 8, color: AppColors.liveGreen),
              SizedBox(width: 6),
              Text('Live', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
            ],
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: isEmpty
                ? const Text('Waiting for the speaker to start talking...',
                    style: TextStyle(fontSize: 16, height: 1.6, color: AppColors.textSecondary))
                : Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: transcript,
                          style: const TextStyle(fontSize: 16, height: 1.6, color: AppColors.textPrimary),
                        ),
                        if (currentPartial.isNotEmpty)
                          TextSpan(
                            text: '${transcript.isEmpty ? '' : ' '}$currentPartial',
                            style: const TextStyle(fontSize: 16, height: 1.6, color: AppColors.textSecondary),
                          ),
                      ],
                    ),
                  ),
          ),
        ),
      ],
    );
  }
}

class _EndedView extends StatelessWidget {
  final String transcript;
  const _EndedView({required this.transcript});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _topBar(
          statusWidget: const Row(
            children: [
              Icon(Icons.circle, size: 8, color: AppColors.idleGrayDot),
              SizedBox(width: 6),
              Text('Session ended', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
            ],
          ),
        ),
        Container(
          width: double.infinity,
          margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: const Color(0xFFF3F4F6), borderRadius: BorderRadius.circular(12)),
          child: const Text(
            'The speaker has ended the session. You can still read the transcript below.',
            style: TextStyle(color: AppColors.textSecondary, fontSize: 13, height: 1.4),
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Text(
              transcript.isEmpty ? 'No transcript available.' : transcript,
              style: const TextStyle(fontSize: 16, height: 1.6),
            ),
          ),
        ),
      ],
    );
  }
}
