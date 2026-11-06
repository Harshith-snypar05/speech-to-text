import 'dart:ui' show PointerDeviceKind;

import 'package:flutter/material.dart';

import '../services/app_settings.dart';
import '../services/connection_status.dart';
import '../services/session_id.dart' show generateSessionId, generateAccessCode;
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

class _SessionScreenState extends State<SessionScreen>
    with SingleTickerProviderStateMixin {
  bool _recording = false;
  bool _connecting = false;
  String? _error;
  ConnectionStatus _connStatus = ConnectionStatus.stopped;
  final List<String> _utterances = [];
  String _currentPartial = '';
  TranscriptionClient? _client;
  late final AnimationController _pulse;
  late final String _sessionId;
  bool _requireAccessCode = false;
  String? _accessCode;

  @override
  void initState() {
    super.initState();
    _sessionId = generateSessionId();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();
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
    final client = TranscriptionClient(
      wsUrl: AppSettings.backendUrl.value,
      sessionId: _sessionId,
      micDeviceId: AppSettings.micDeviceId.value,
      accessCode: _accessCode,
    );
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
    final code = _accessCode;
    final link =
        '${viewerLinkOrigin()}/#/viewer?session=$_sessionId${code != null ? '&code=$code' : ''}';
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => ShareLinkSheet(link: link, accessCode: code),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    final color = _recording ? colors.recordRed : colors.primaryBlue;

    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            _mainColumn(colors, color),
            Positioned.fill(
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

  Widget _mainColumn(AppColors colors, Color color) {
    return Column(
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
                      icon: Icon(
                        Icons.settings_outlined,
                        color: colors.textPrimary,
                      ),
                      onPressed: () =>
                          Navigator.of(context).pushNamed('/settings'),
                    ),
                    Stack(
                      clipBehavior: Clip.none,
                      children: [
                        IconButton(
                          icon: Icon(
                            Icons.ios_share,
                            color: colors.textPrimary,
                          ),
                          onPressed: _openShareSheet,
                        ),
                        Positioned(
                          right: 6,
                          top: 6,
                          child: Container(
                            width: 9,
                            height: 9,
                            decoration: BoxDecoration(
                              color: _recording
                                  ? colors.liveGreen
                                  : const Color(0xFFFFC107),
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
                      decoration: BoxDecoration(
                        color: color,
                        shape: BoxShape.circle,
                      ),
                      child: _connecting
                          ? const Padding(
                              padding: EdgeInsets.all(28),
                              child: CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 3,
                              ),
                            )
                          : const Icon(
                              Icons.mic,
                              color: Colors.white,
                              size: 40,
                            ),
                    ),
                  ],
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 16),
        Text(
          _connecting
              ? 'Connecting...'
              : (_recording ? 'Tap to stop' : 'Tap to start'),
          style: TextStyle(color: colors.textSecondary, fontSize: 14),
        ),
        if (!_recording && !_connecting) ...[
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                'Require access code',
                style: TextStyle(color: colors.textSecondary, fontSize: 13),
              ),
              Switch(
                value: _requireAccessCode,
                onChanged: (v) => setState(() {
                  _requireAccessCode = v;
                  _accessCode = v ? generateAccessCode() : null;
                }),
              ),
            ],
          ),
        ],
        if (_recording) ...[
          const SizedBox(height: 12),
          TextButton.icon(
            onPressed: _endSession,
            icon: Icon(
              Icons.stop_circle_outlined,
              color: colors.recordRed,
              size: 18,
            ),
            label: Text(
              'End Session',
              style: TextStyle(
                color: colors.recordRed,
                fontWeight: FontWeight.w700,
              ),
            ),
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
                  style: TextStyle(color: colors.recordRed, fontSize: 13),
                ),
                if (_connStatus == ConnectionStatus.connectionFailed) ...[
                  const SizedBox(height: 4),
                  TextButton(
                    onPressed: _retryConnection,
                    child: Text(
                      'Retry',
                      style: TextStyle(
                        color: colors.primaryBlue,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
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
            child: Text(
              _error!,
              textAlign: TextAlign.center,
              style: TextStyle(color: colors.recordRed, fontSize: 13),
            ),
          ),
        ],
      ],
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
      case ConnectionStatus.unauthorized:
        return 'Rejected by the server (access code issue). Recording has stopped transcribing.';
      default:
        return '';
    }
  }

  Widget _ring(Color color, double size, double opacity) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color.withValues(alpha: opacity),
      ),
    );
  }
}

/// Drag the handle up to reveal the transcript; collapsed, only the
/// "Transcription / Live|Ready" header strip shows (see the screenshot
/// this was built from). Scrolls itself to the bottom as new text comes
/// in so an expanded sheet behaves like a live auto-scrolling log.
class _TranscriptionSheet extends StatefulWidget {
  final bool recording;
  final String transcript;
  final String currentPartial;
  const _TranscriptionSheet({
    required this.recording,
    required this.transcript,
    required this.currentPartial,
  });

  @override
  State<_TranscriptionSheet> createState() => _TranscriptionSheetState();
}

class _TranscriptionSheetState extends State<_TranscriptionSheet> {
  static const _collapsedSize = 0.1;
  static const _expandedSize = 0.85;

  ScrollController? _scrollController;

  @override
  void didUpdateWidget(covariant _TranscriptionSheet old) {
    super.didUpdateWidget(old);
    if (widget.transcript != old.transcript ||
        widget.currentPartial != old.currentPartial) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
    }
  }

  void _scrollToBottom() {
    final controller = _scrollController;
    if (controller == null || !controller.hasClients) return;
    final position = controller.position;
    // Lands with the latest text roughly in the lower half of the screen
    // rather than jammed against the very bottom edge.
    final target = (position.maxScrollExtent - position.viewportDimension * 0.4)
        .clamp(0.0, position.maxScrollExtent);
    controller.animateTo(
      target,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    // The default ScrollBehavior only accepts touch for drag-to-scroll/
    // resize -- without this override, dragging the handle with a mouse
    // (desktop browser, e.g. testing over the Cloudflare tunnel) does
    // nothing even though the exact same drag works fine on a touchscreen.
    return ScrollConfiguration(
      behavior: _MouseDragScrollBehavior(),
      child: DraggableScrollableSheet(
        initialChildSize: _collapsedSize,
        minChildSize: _collapsedSize,
        maxChildSize: _expandedSize,
        snap: true,
        snapSizes: const [_collapsedSize, _expandedSize],
        builder: (context, scrollController) {
          _scrollController = scrollController;
          return ValueListenableBuilder<TranscriptionMode>(
            valueListenable: AppSettings.transcriptionMode,
            builder: (context, mode, _) {
              // "Accurate (per-sentence)" mode hides the in-progress partial
              // and only shows committed finals -- same relay messages either
              // way, this is purely a client-side display choice.
              final showPartial = mode == TranscriptionMode.live;
              final isEmpty =
                  widget.transcript.isEmpty &&
                  (!showPartial || widget.currentPartial.isEmpty);
              return Container(
                decoration: BoxDecoration(
                  color: colors.surface,
                  borderRadius: const BorderRadius.vertical(
                    top: Radius.circular(24),
                  ),
                  boxShadow: const [
                    BoxShadow(
                      color: Color(0x14000000),
                      blurRadius: 16,
                      offset: Offset(0, -4),
                    ),
                  ],
                ),
                child: ListView(
                  controller: scrollController,
                  padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
                  children: [
                    Center(
                      child: Container(
                        width: 36,
                        height: 4,
                        margin: const EdgeInsets.only(bottom: 16),
                        decoration: BoxDecoration(
                          color: colors.cardBorder,
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Transcription',
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 16,
                            color: colors.textPrimary,
                          ),
                        ),
                        Row(
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              decoration: BoxDecoration(
                                color: colors.primaryBlue,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              widget.recording ? 'Live' : 'Ready',
                              style: TextStyle(
                                color: colors.textSecondary,
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    if (isEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 56,
                              height: 56,
                              decoration: BoxDecoration(
                                color: colors.lightBlueBg,
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                Icons.graphic_eq,
                                color: colors.primaryBlue,
                              ),
                            ),
                            const SizedBox(height: 16),
                            Text(
                              'Start speaking...',
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 15,
                                color: colors.textPrimary,
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              'Your words will appear here in real time.',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: colors.textSecondary,
                                fontSize: 13,
                              ),
                            ),
                          ],
                        ),
                      )
                    else
                      Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: widget.transcript,
                              style: TextStyle(
                                fontSize: 15,
                                height: 1.5,
                                color: colors.textPrimary,
                              ),
                            ),
                            if (showPartial && widget.currentPartial.isNotEmpty)
                              TextSpan(
                                text:
                                    '${widget.transcript.isEmpty ? '' : ' '}${widget.currentPartial}',
                                style: TextStyle(
                                  fontSize: 15,
                                  height: 1.5,
                                  color: colors.textSecondary,
                                ),
                              ),
                          ],
                        ),
                      ),
                  ],
                ),
              );
            },
          );
        },
      ),
    );
  }
}

class _MouseDragScrollBehavior extends MaterialScrollBehavior {
  @override
  Set<PointerDeviceKind> get dragDevices => {
    PointerDeviceKind.touch,
    PointerDeviceKind.mouse,
    PointerDeviceKind.stylus,
    PointerDeviceKind.trackpad,
  };
}
