import 'package:flutter/material.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../config/app_config.dart';
import '../services/app_settings.dart';
import '../services/auth_service.dart';
import '../services/connection_status.dart';
import '../services/platform_api.dart';
import '../services/session_id.dart' show generateSessionId, generateAccessCode;
import '../services/transcription_client.dart';
import '../services/transcript_storage.dart';
import '../theme.dart';
import '../widgets/brand.dart';
import '../widgets/waveform.dart';
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
  bool _paused = false;
  String? _error;
  ConnectionStatus _connStatus = ConnectionStatus.stopped;
  final List<String> _utterances = [];
  String _currentPartial = '';
  final List<double> _levels = [];
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

  Future<void> _start() async {
    setState(() {
      _connecting = true;
      _error = null;
      _utterances.clear();
      _currentPartial = '';
      _levels.clear();
      _paused = false;
    });
    final client = TranscriptionClient(
      wsUrl: AppSettings.backendUrl.value,
      sessionId: _sessionId,
      micDeviceId: AppSettings.micDeviceId.value,
      accessCode: _accessCode,
      authToken: AuthService.token,
    );
    client.onText.listen((text) {
      if (mounted) setState(() => _utterances.add(text));
    });
    client.onPartial.listen((text) {
      if (mounted) setState(() => _currentPartial = text);
    });
    client.onRefine.listen((r) {
      if (!mounted) return;
      final i = _utterances.lastIndexOf(r.original);
      if (i >= 0) setState(() => _utterances[i] = r.refined);
    });
    client.onLevel.listen((v) {
      if (!mounted) return;
      setState(() {
        _levels.add(v);
        if (_levels.length > 160) _levels.removeRange(0, _levels.length - 80);
      });
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
      if (AppSettings.preventAutoLock.value) WakelockPlus.enable().catchError((_) {});
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

  Future<void> _togglePause() async {
    final client = _client;
    if (client == null || !_recording) return;
    if (_paused) {
      await client.resume();
      if (AppSettings.preventAutoLock.value) WakelockPlus.enable().catchError((_) {});
    } else {
      await client.pause();
      WakelockPlus.disable().catchError((_) {});
    }
    if (!mounted) return;
    setState(() {
      _paused = client.isPaused;
      if (_paused) {
        _currentPartial = '';
        _levels.clear();
      }
    });
  }

  Future<void> _stop() async {
    WakelockPlus.disable().catchError((_) {});
    await _client?.stop();
    final saved = await TranscriptStorage.save(_transcript);
    setState(() {
      _recording = false;
      _paused = false;
      _client = null;
      _currentPartial = '';
      _levels.clear();
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

  /// Signed-in accounts share the same backend-tracked link the web app and transcript history use
  /// (`https://host/s/TOKEN`, backed by `POST /v1/sessions/ID/share`) -- the relay already created this
  /// session's row the moment recording started, so the share token works immediately, live or not.
  /// Without an account there is no backend session row to attach a token to, so that case falls back to
  /// a direct link into the relay's own viewer role (session id + optional access code, no server state).
  Future<void> _openShareSheet() async {
    if (AppConfig.platformMode && AuthService.token != null) {
      try {
        final shared = await PlatformApi.share(_sessionId);
        if (mounted && shared.shareUrl != null) {
          showModalBottomSheet(
            context: context,
            isScrollControlled: true,
            backgroundColor: Colors.transparent,
            builder: (_) => ShareLinkSheet(link: shared.shareUrl!),
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not create the share link: $e')));
        }
      }
      return;
    }
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

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            _topBar(colors),
            // Transcript fills the top and follows the newest text; it is not a draggable sheet.
            Expanded(
              child: _TranscriptPanel(
                recording: _recording,
                paused: _paused,
                transcript: _transcript,
                currentPartial: _currentPartial,
              ),
            ),
            _controls(colors),
          ],
        ),
      ),
    );
  }

  Widget _topBar(AppColors colors) {
    return SizedBox(
      height: 64,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                IconButton(
                  icon: Icon(Icons.settings_outlined, color: colors.textPrimary),
                  onPressed: () => Navigator.of(context).pushNamed('/settings'),
                ),
                Stack(
                  clipBehavior: Clip.none,
                  children: [
                    IconButton(
                      icon: Icon(Icons.ios_share, color: colors.textPrimary),
                      onPressed: _openShareSheet,
                    ),
                    Positioned(
                      right: 6,
                      top: 6,
                      child: Container(
                        width: 9,
                        height: 9,
                        decoration: BoxDecoration(
                          color: _recording ? colors.liveGreen : const Color(0xFFFFC107),
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const IgnorePointer(child: ScriptLivMark(size: 44)),
        ],
      ),
    );
  }

  /// Bottom dock: waveform, then the mic. Before a session the mic starts it; once recording, the mic becomes a
  /// status indicator flanked by Pause/Resume and End Session.
  Widget _controls(AppColors colors) {
    final active = _recording && !_paused;
    final micColor = !_recording
        ? colors.primaryBlue
        : (_paused ? const Color(0xFFF59E0B) : colors.recordRed);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 14),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        boxShadow: const [BoxShadow(color: Color(0x14000000), blurRadius: 16, offset: Offset(0, -4))],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Waveform(
            levels: _levels,
            active: active && _connStatus == ConnectionStatus.connected,
            height: 48,
          ),
          const SizedBox(height: 10),
          if (_recording)
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _actionButton(
                  key: const Key('pause_resume_button'),
                  icon: _paused ? Icons.play_arrow_rounded : Icons.pause_rounded,
                  label: _paused ? 'Resume' : 'Pause',
                  color: colors.primaryBlue,
                  onTap: _togglePause,
                ),
                _micButton(micColor, tappable: false),
                _actionButton(
                  key: const Key('end_session_button'),
                  icon: Icons.stop_rounded,
                  label: 'End Session',
                  color: colors.recordRed,
                  onTap: _endSession,
                ),
              ],
            )
          else ...[
            _micButton(micColor, tappable: !_connecting),
            const SizedBox(height: 6),
            Text(
              _connecting ? 'Connecting...' : 'Tap to start',
              style: TextStyle(color: colors.textSecondary, fontSize: 14),
            ),
            if (!_connecting)
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text('Require access code', style: TextStyle(color: colors.textSecondary, fontSize: 13)),
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
          if (_recording && _paused)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                'Paused. Nothing is being transcribed or counted against your minutes.',
                textAlign: TextAlign.center,
                style: TextStyle(color: colors.textSecondary, fontSize: 12),
              ),
            ),
          if (_recording && _connStatus != ConnectionStatus.connected)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Column(
                children: [
                  Text(
                    _statusMessage(_connStatus),
                    textAlign: TextAlign.center,
                    style: TextStyle(color: colors.recordRed, fontSize: 13),
                  ),
                  if (_connStatus == ConnectionStatus.connectionFailed)
                    TextButton(
                      onPressed: _retryConnection,
                      child: Text(
                        'Retry',
                        style: TextStyle(color: colors.primaryBlue, fontWeight: FontWeight.w700),
                      ),
                    ),
                ],
              ),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _error!,
                textAlign: TextAlign.center,
                style: TextStyle(color: colors.recordRed, fontSize: 13),
              ),
            ),
        ],
      ),
    );
  }

  Widget _micButton(Color color, {required bool tappable}) {
    return GestureDetector(
      key: const Key('mic_button'),
      onTap: tappable ? _start : null,
      child: AnimatedBuilder(
        animation: _pulse,
        builder: (context, _) {
          final pulsing = _recording && !_paused;
          return SizedBox(
            width: 112,
            height: 112,
            child: Stack(
              alignment: Alignment.center,
              children: [
                _ring(color, 112, 0.12),
                _ring(color, pulsing ? 88 + 18 * _pulse.value : 88, 0.18),
                Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                  child: _connecting
                      ? const Padding(
                          padding: EdgeInsets.all(18),
                          child: CircularProgressIndicator(color: Colors.white, strokeWidth: 3),
                        )
                      : Icon(_paused ? Icons.mic_off : Icons.mic, color: Colors.white, size: 30),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _actionButton({
    required Key key,
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
  }) {
    return Padding(
      padding: const EdgeInsets.only(top: 22),
      child: GestureDetector(
        key: key,
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: SizedBox(
          width: 84,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 54,
                height: 54,
                decoration: BoxDecoration(color: color.withValues(alpha: 0.12), shape: BoxShape.circle),
                child: Icon(icon, color: color, size: 28),
              ),
              const SizedBox(height: 6),
              Text(
                label,
                textAlign: TextAlign.center,
                style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w700),
              ),
            ],
          ),
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
      case ConnectionStatus.unauthorized:
        return 'Rejected by the server (access code issue). Recording has stopped transcribing.';
      case ConnectionStatus.outOfMinutes:
        switch (_client?.closeReason) {
          case 'allowance_reserved':
            return 'Your minutes are in use by another recording. Stop it, then start again.';
          case 'payment_required':
            if (!AppConfig.showSubscriptions) return 'Recording is paused on your account. Contact support to get it back.';
            return 'Payment required. Your last payment failed, so paid minutes are paused. Update your payment method on the website, then retry.';
          case 'session_limit':
            if (UsageInfo.lastOfferActive) return 'Sessions are limited to 4 hours. Your transcript is saved. Start a new session to keep going.';
            if (!AppConfig.showSubscriptions) return 'This session reached its time limit. Your transcript is saved. Start a new session to keep going.';
            return 'Free sessions are limited to 30 minutes. Your transcript is saved. Start a new session to keep going, or upgrade to Pro for longer sessions.';
          case 'personal_limit':
            return 'You reached your personal limit. Recording stopped. Raise the limit in Settings to continue.';
          default:
            if (UsageInfo.lastOfferActive) return 'You have used your free offer minutes. Recording stopped exactly when they ran out. Your transcript is saved.';
            if (!AppConfig.showSubscriptions) return 'You are out of minutes. Recording stopped exactly when your balance ran out. Your transcript is saved.';
            return 'You are out of minutes. Recording stopped exactly when your balance ran out; add minutes or upgrade to continue.';
        }
      case ConnectionStatus.emailNotVerified:
        return 'Verify your email to record. Open the verification link we sent you, or request a new one in Settings.';
      case ConnectionStatus.superseded:
        return 'This recording continued on another connection. Your transcript so far is saved.';
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

/// Fixed (not draggable) transcript area at the top of the screen. It keeps the newest text in view: whenever
/// text arrives and the reader is at (or near) the bottom, it scrolls down. Scrolling up to re-read pauses the
/// following until the reader returns to the bottom.
class _TranscriptPanel extends StatefulWidget {
  final bool recording;
  final bool paused;
  final String transcript;
  final String currentPartial;
  const _TranscriptPanel({
    required this.recording,
    required this.paused,
    required this.transcript,
    required this.currentPartial,
  });

  @override
  State<_TranscriptPanel> createState() => _TranscriptPanelState();
}

class _TranscriptPanelState extends State<_TranscriptPanel> {
  static const _followSlack = 96.0;
  final ScrollController _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  bool get _nearBottom =>
      !_scroll.hasClients || _scroll.position.maxScrollExtent - _scroll.offset <= _followSlack;

  @override
  void didUpdateWidget(covariant _TranscriptPanel old) {
    super.didUpdateWidget(old);
    if (widget.transcript != old.transcript || widget.currentPartial != old.currentPartial) {
      // Decide before the new text is laid out: were we following the end?
      final follow = _nearBottom;
      if (follow) WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
    }
  }

  void _scrollToBottom() {
    if (!_scroll.hasClients) return;
    _scroll.animateTo(
      _scroll.position.maxScrollExtent,
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    final stateColor = widget.paused ? const Color(0xFFF59E0B) : colors.primaryBlue;
    final stateLabel = widget.recording ? (widget.paused ? 'Paused' : 'Live') : 'Ready';
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Transcription',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: colors.textPrimary),
              ),
              Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(color: stateColor, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    stateLabel,
                    style: TextStyle(color: colors.textSecondary, fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          Expanded(
            child: ValueListenableBuilder<TranscriptionMode>(
              valueListenable: AppSettings.transcriptionMode,
              builder: (context, mode, _) {
                // "Accurate (per-sentence)" mode hides the in-progress partial and only shows committed
                // finals -- a client-side display choice, the relay sends the same messages either way.
                final showPartial = mode == TranscriptionMode.live;
                final isEmpty = widget.transcript.isEmpty && (!showPartial || widget.currentPartial.isEmpty);
                if (isEmpty) return _empty(colors);
                return SingleChildScrollView(
                  key: const Key('transcript_scroll'),
                  controller: _scroll,
                  child: SizedBox(
                    width: double.infinity,
                    child: Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: widget.transcript,
                            style: TextStyle(fontSize: 16, height: 1.55, color: colors.textPrimary),
                          ),
                          if (showPartial && widget.currentPartial.isNotEmpty)
                            TextSpan(
                              text: '${widget.transcript.isEmpty ? '' : ' '}${widget.currentPartial}',
                              style: TextStyle(fontSize: 16, height: 1.55, color: colors.textSecondary),
                            ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _empty(AppColors colors) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(color: colors.lightBlueBg, shape: BoxShape.circle),
            child: Icon(Icons.graphic_eq, color: colors.primaryBlue),
          ),
          const SizedBox(height: 16),
          Text(
            'Start speaking...',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: colors.textPrimary),
          ),
          const SizedBox(height: 6),
          Text(
            'Your words will appear here in real time.',
            textAlign: TextAlign.center,
            style: TextStyle(color: colors.textSecondary, fontSize: 13),
          ),
        ],
      ),
    );
  }
}
