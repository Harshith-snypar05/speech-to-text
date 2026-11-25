import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../config/app_config.dart';
import '../services/platform_api.dart';
import '../theme.dart';
import '../widgets/brand.dart';

/// One saved session of the signed-in account: transcript, share on/off with a copyable link, delete.
class PlatformSessionScreen extends StatefulWidget {
  final String sessionId;
  const PlatformSessionScreen({super.key, required this.sessionId});
  @override
  State<PlatformSessionScreen> createState() => _PlatformSessionScreenState();
}

class _PlatformSessionScreenState extends State<PlatformSessionScreen> {
  late Future<SessionItem> _item = PlatformApi.session(widget.sessionId);
  bool _busy = false;

  void _toast(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _toggleShare(SessionItem s) async {
    setState(() => _busy = true);
    try {
      final next = s.sharing ? await PlatformApi.unshare(s.id) : await PlatformApi.share(s.id);
      if (mounted) setState(() => _item = Future.value(SessionItem(next.id, next.title, next.startedAt, next.endedAt, next.sharing, next.shareUrl, s.transcript)));
    } on ApiException catch (e) {
      if (mounted) _toast(e.message);
    } catch (_) {
      if (mounted) _toast('Could not update sharing. Check your connection.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete(SessionItem s) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete this transcript?'),
        content: const Text('This removes it and any shared link. It cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await PlatformApi.deleteSession(s.id);
      if (mounted) Navigator.pop(context);
    } catch (_) {
      if (mounted) _toast('Could not delete. Try again.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Transcript', style: TextStyle(fontSize: 16))),
      body: FutureBuilder<SessionItem>(
        future: _item,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snap.hasError) {
            return Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text('Could not load this transcript.', style: TextStyle(color: c.recordRed)),
                TextButton(onPressed: () => setState(() => _item = PlatformApi.session(widget.sessionId)), child: const Text('Retry')),
              ]),
            );
          }
          final s = snap.data!;
          return Column(children: [
            if (s.sharing && s.shareUrl != null)
              ListTile(
                leading: const Icon(Icons.link),
                title: Text(s.shareUrl!, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13)),
                trailing: IconButton(
                  icon: const Icon(Icons.copy),
                  tooltip: 'Copy link',
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: s.shareUrl!));
                    if (mounted) _toast('Link copied');
                  },
                ),
              ),
            Expanded(
              child: s.transcript.isEmpty
                  ? Center(child: Text('No transcript text was recorded for this session.', style: TextStyle(color: c.textSecondary)))
                  : ListView.separated(
                      padding: const EdgeInsets.all(20),
                      itemCount: s.transcript.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 12),
                      itemBuilder: (_, i) => SelectableText(s.transcript[i], style: TextStyle(fontSize: 16, height: 1.5, color: c.textPrimary)),
                    ),
            ),
            SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Row(children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: s.transcript.isEmpty ? null : () => SharePlus.instance.share(ShareParams(text: s.transcript.join('\n'), subject: 'ScriptLiv transcript')),
                        icon: const Icon(Icons.ios_share),
                        label: const Text('Share text'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _busy ? null : () => _toggleShare(s),
                        icon: const Icon(Icons.link),
                        label: Text(s.sharing ? 'Stop sharing' : 'Share link'),
                      ),
                    ),
                  ]),
                  TextButton(onPressed: () => _delete(s), child: Text('Delete transcript', style: TextStyle(color: c.recordRed))),
                  Text(AppConfig.copyright, style: TextStyle(color: c.textSecondary, fontSize: 11)),
                ]),
              ),
            ),
          ]);
        },
      ),
    );
  }
}

/// Opened from a shared link (scriptliv://s/TOKEN or https://.../s/TOKEN). Needs no account.
/// Polls the platform API: every second while the session is live, slower afterwards.
class SharedViewScreen extends StatefulWidget {
  final String token;

  /// Test seam: replaces the network fetch. Production code leaves this null.
  @visibleForTesting
  final Future<SharedView> Function(String token)? fetcher;
  const SharedViewScreen({super.key, required this.token, this.fetcher});
  @override
  State<SharedViewScreen> createState() => _SharedViewScreenState();
}

class _SharedViewScreenState extends State<SharedViewScreen> {
  SharedView? _view;
  String? _error;
  Timer? _timer;

  // Instagram-Explore-style header: slides away on scroll down, back on scroll up (or near the
  // top) -- matches the web viewer at scriptliv_web/app/s/[token]/page.tsx. 6px avoids flicker
  // from sub-pixel scroll jitter, same threshold as the web version.
  bool _headerHidden = false;
  static const _scrollHideThreshold = 6.0;

  // True only while the current scroll gesture was started or taken over by the user's finger
  // (including the fling that follows). Programmatic scrolls -- the live auto-follow animateTo /
  // jumpTo -- never set it, so they cannot hide the header.
  bool _userScroll = false;

  // Live sessions follow the newest text. Following pauses when the viewer scrolls up to
  // re-read, and resumes once they scroll back near the bottom.
  final _scrollController = ScrollController();
  bool _follow = true;
  static const _followSlack = 80.0;

  @override
  void initState() {
    super.initState();
    _poll();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _scrollController.dispose();
    super.dispose();
  }

  void _followLatest() {
    if (!_follow) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      final position = _scrollController.position;
      _scrollController
          .animateTo(position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut)
          .whenComplete(() {
        // ListView estimates the extent of items it has not built yet, so the first pass can
        // stop short; settle on the real end.
        if (mounted && _scrollController.hasClients && _follow) {
          final p = _scrollController.position;
          if (p.pixels < p.maxScrollExtent - 1) _scrollController.jumpTo(p.maxScrollExtent);
        }
      });
    });
  }

  Future<void> _poll() async {
    try {
      final v = await (widget.fetcher ?? PlatformApi.shared)(widget.token);
      if (!mounted) return;
      setState(() {
        _view = v;
        _error = null;
      });
      if (v.live) _followLatest();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.status == 404 ? 'This link is no longer available.' : e.message);
      if (e.status == 404) return;
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Could not reach the server. Retrying...');
    }
    _timer?.cancel();
    _timer = Timer(Duration(seconds: (_view?.live ?? false) ? 1 : 15), _poll);
  }

  bool _onScrollNotification(ScrollNotification n) {
    if (n is ScrollStartNotification) {
      _userScroll = n.dragDetails != null;
    } else if (n is ScrollUpdateNotification && n.dragDetails != null) {
      _userScroll = true; // finger took over (possibly interrupting an auto-follow animation)
    }
    if (n is ScrollUpdateNotification && n.dragDetails != null) {
      _follow = n.metrics.extentAfter < _followSlack;
    } else if (n is ScrollEndNotification) {
      _follow = n.metrics.extentAfter < _followSlack;
    }
    if (n is ScrollUpdateNotification) {
      final pixels = n.metrics.pixels;
      final delta = n.scrollDelta ?? 0;
      if (pixels <= _scrollHideThreshold) {
        if (_headerHidden) setState(() => _headerHidden = false);
      } else if (_userScroll && delta > _scrollHideThreshold) {
        if (!_headerHidden) setState(() => _headerHidden = true);
      } else if (_userScroll && delta < -_scrollHideThreshold) {
        if (_headerHidden) setState(() => _headerHidden = false);
      }
    }
    if (n is ScrollEndNotification) _userScroll = false;
    return false;
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final v = _view;
    return Scaffold(
      // Transparent, not themed/elevated like a default AppBar -- the wave backdrop behind every
      // screen (see WaveBackdrop) shows through instead of a boxed bar sitting on top of it.
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: v == null
            ? Center(child: _error == null ? const CircularProgressIndicator() : Text(_error!, style: TextStyle(color: c.recordRed)))
            : Column(
                children: [
                  Expanded(
                    // Clip: the slid-away header is only translated, so without this it paints
                    // above the Stack -- into the status-bar area.
                    child: ClipRect(
                      child: Stack(
                        children: [
                          NotificationListener<ScrollNotification>(
                            onNotification: _onScrollNotification,
                            child: v.transcript.isEmpty
                                ? Center(
                                    child: Padding(
                                      padding: const EdgeInsets.fromLTRB(24, 64, 24, 24),
                                      child: Text(v.live ? 'Waiting for the speaker...' : 'No transcript text.', style: TextStyle(color: c.textSecondary)),
                                    ),
                                  )
                                : ListView.separated(
                                    controller: _scrollController,
                                    padding: const EdgeInsets.fromLTRB(20, 64, 20, 20),
                                    itemCount: v.transcript.length,
                                    separatorBuilder: (_, __) => const SizedBox(height: 12),
                                    itemBuilder: (_, i) => Text(v.transcript[i], style: TextStyle(fontSize: 16, height: 1.5, color: c.textPrimary)),
                                  ),
                          ),
                          Positioned(
                            top: 0,
                            left: 0,
                            right: 0,
                            child: AnimatedSlide(
                              duration: const Duration(milliseconds: 250),
                              curve: Curves.easeOut,
                              offset: _headerHidden ? const Offset(0, -1) : Offset.zero,
                              // No background fill here -- WaveBackdrop is never a flat color (it's
                              // wave art + a haze gradient), so any solid/gradient fill on this row
                              // reads as a separate boxed layer sitting on top of it. Every other
                              // screen floats its top-bar icons directly on the backdrop with no
                              // panel behind them (see session_screen.dart); matching that here.
                              child: Padding(
                                padding: const EdgeInsets.fromLTRB(16, 10, 16, 16),
                                child: Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    const ScriptLivLogo(height: 22),
                                    Row(
                                      children: [
                                        Icon(Icons.circle, size: 8, color: v.live ? c.recordRed : c.textSecondary),
                                        const SizedBox(width: 6),
                                        Text(v.live ? 'Live' : 'Ended', style: TextStyle(color: c.textSecondary, fontSize: 13, fontWeight: FontWeight.w600)),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  Padding(padding: const EdgeInsets.all(8), child: Text(AppConfig.copyright, style: TextStyle(color: c.textSecondary, fontSize: 11))),
                ],
              ),
      ),
    );
  }
}
