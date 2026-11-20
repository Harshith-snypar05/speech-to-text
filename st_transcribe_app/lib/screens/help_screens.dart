import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../config/app_config.dart';
import '../services/platform_api.dart';
import '../theme.dart';

const _contactEmail = 'info@scriptliv.com';

Widget _screen(BuildContext context, String title, Widget body) {
  final c = AppColors.of(context);
  return Scaffold(
    appBar: AppBar(
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
      automaticallyImplyLeading: false,
      leading: BackButton(color: c.textPrimary),
    ),
    body: body,
  );
}

// ------------------------------------------------------------------ Request a feature

class RequestFeatureScreen extends StatefulWidget {
  const RequestFeatureScreen({super.key});
  @override
  State<RequestFeatureScreen> createState() => _RequestFeatureScreenState();
}

class _RequestFeatureScreenState extends State<RequestFeatureScreen> {
  final _title = TextEditingController();
  final _message = TextEditingController();
  String _kind = 'feature';
  bool _busy = false;
  bool _sent = false;
  String? _error;

  @override
  void dispose() {
    _title.dispose();
    _message.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final title = _title.text.trim();
    if (title.isEmpty) {
      setState(() => _error = 'Give your request a short title.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await PlatformApi.sendFeedback(_kind, title, _message.text.trim());
      if (mounted) setState(() => _sent = true);
    } on ApiException catch (e) {
      // Server without the feedback endpoint (or offline): fall back to email so the idea is never lost.
      if (e.status == 404 || e.status == 405 || e.status >= 500) {
        await _viaEmail(title);
      } else if (mounted) {
        setState(() => _error = e.message);
      }
    } catch (_) {
      await _viaEmail(title);
    }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _viaEmail(String title) async {
    final uri = Uri(scheme: 'mailto', path: _contactEmail, queryParameters: {'subject': 'ScriptLiv: $title', 'body': _message.text.trim()});
    final ok = await launchUrl(uri);
    if (mounted && !ok) setState(() => _error = 'Could not send. Email $_contactEmail instead.');
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return _screen(
      context,
      'Request a feature',
      _sent
          ? Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.check_circle_outline, size: 56, color: c.liveGreen),
                  const SizedBox(height: 14),
                  Text('Thank you!', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: c.textPrimary)),
                  const SizedBox(height: 6),
                  Text('Your suggestion reached the team. We read every one.', textAlign: TextAlign.center, style: TextStyle(color: c.textSecondary)),
                  const SizedBox(height: 20),
                  FilledButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Done')),
                ],
              ),
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text('Tell us what would make ScriptLiv better.', style: TextStyle(color: c.textSecondary)),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 8,
                  children: [
                    for (final k in const [('feature', 'Feature idea'), ('bug', 'Problem'), ('other', 'Other')])
                      ChoiceChip(label: Text(k.$2), selected: _kind == k.$1, onSelected: (_) => setState(() => _kind = k.$1)),
                  ],
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: _title,
                  maxLength: 120,
                  decoration: const InputDecoration(labelText: 'Title', border: OutlineInputBorder()),
                  textCapitalization: TextCapitalization.sentences,
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _message,
                  maxLength: 4000,
                  minLines: 5,
                  maxLines: 8,
                  decoration: const InputDecoration(labelText: 'Details (optional)', alignLabelWithHint: true, border: OutlineInputBorder()),
                  textCapitalization: TextCapitalization.sentences,
                ),
                if (_error != null) Padding(padding: const EdgeInsets.only(bottom: 8), child: Text(_error!, style: TextStyle(color: c.recordRed))),
                FilledButton(onPressed: _busy ? null : _send, child: Text(_busy ? 'Sending...' : 'Send')),
              ],
            ),
    );
  }
}

// ------------------------------------------------------------------ Fix a connection issue

class _Fix {
  final String problem;
  final List<String> steps;
  const _Fix(this.problem, this.steps);
}

const _fixes = [
  _Fix('"Could not reach the server"', [
    'Check that your phone has internet (open any website).',
    'Switch between Wi-Fi and mobile data and try again.',
    'If you use a VPN or a work/school network, turn it off or try another network; some block live connections.',
    'Wait a minute and retry. If it keeps failing, the service may be updating; email $_contactEmail.',
  ]),
  _Fix('Live transcript does not start or keeps disconnecting', [
    'Make sure the app has Microphone permission: Settings > Apps > ScriptLiv > Permissions.',
    'Move to a place with steadier signal; live transcription needs a continuous connection.',
    'Stop the session and start a new one. Your text so far is saved in Transcripts.',
    'Turn off battery saver for ScriptLiv so Android does not pause it in the background.',
  ]),
  _Fix('No words appear while I speak', [
    'Check you are not muted and the right microphone is chosen in Settings > Microphone.',
    'Close other apps that use the microphone (calls, voice recorders).',
    'Speak close to the phone and reduce background noise.',
    'Unplug or reconnect Bluetooth headsets, then try again.',
  ]),
  _Fix('"Session expired. Sign in again."', [
    'This happens after you change your password, or if you signed in on another device and signed out all others.',
    'Log out from Settings, then sign in again with your new password.',
  ]),
  _Fix('Shared link will not open for viewers', [
    'Make sure sharing is turned on for the session.',
    'Send the full link, not a shortened or edited one.',
    'Viewers need an internet connection; they do not need an account.',
  ]),
  _Fix('I did not get the verification or reset email', [
    'Check the Spam / Promotions folder.',
    'Make sure you typed the right address, then ask for a new link; links expire after 24 hours.',
    'Still nothing after a few minutes? Email $_contactEmail from that address.',
  ]),
  if (AppConfig.showSubscriptions)
    _Fix('Out of minutes or "Payment required"', [
      'Open Settings > Usage to see what is left, or Settings > Membership for payment status.',
      'Fix a failed payment on the website via Change plan, or wait for your minutes to reset on the date shown.',
    ])
  else
    _Fix('Out of minutes', [
      'Open Settings > Usage to see how many minutes you have left.',
      'Still stuck? Email $_contactEmail from your account address and we will help.',
    ]),
];

class ConnectionHelpScreen extends StatelessWidget {
  const ConnectionHelpScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return _screen(
      context,
      'Fix a connection issue',
      ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Find your problem below and follow the steps.', style: TextStyle(color: c.textSecondary)),
          const SizedBox(height: 12),
          for (final f in _fixes)
            Container(
              margin: const EdgeInsets.only(bottom: 10),
              decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(14), border: Border.all(color: c.cardBorder)),
              child: Theme(
                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  title: Text(f.problem, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: c.textPrimary)),
                  childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                  expandedCrossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (var i = 0; i < f.steps.length; i++)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('${i + 1}.  ', style: TextStyle(fontWeight: FontWeight.w700, color: c.primaryBlue)),
                            Expanded(child: Text(f.steps[i], style: TextStyle(fontSize: 13.5, height: 1.35, color: c.textPrimary))),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
          if (AppConfig.platformMode)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text('Still stuck? Email $_contactEmail and tell us what you see.', style: TextStyle(color: c.textSecondary, fontSize: 13)),
            ),
        ],
      ),
    );
  }
}

// ------------------------------------------------------------------ Privacy policy / Terms

class _Para {
  final String? lead; // bold lead-in
  final String text;
  final bool bullet;
  const _Para(this.text, {this.lead, this.bullet = false});
}

class _Sec {
  final String title;
  final List<_Para> body;
  const _Sec(this.title, this.body);
}

const _privacy = [
  _Sec('What we collect', [
    _Para('Your name, email address and a securely hashed password. We never store your password in readable form.', lead: 'Account details.'),
    _Para('When you record, your microphone audio is streamed to our transcription service and turned into text. We do not keep your audio recordings. We keep the resulting transcript so you can read, rename, share and delete it.', lead: 'Your speech and transcripts.'),
    _Para('How many seconds each session used, when it started and ended. We need this to count your minutes and apply limits.', lead: 'Usage records.'),
    _Para('Preferences such as theme, text size and your personal minute limit.', lead: 'Settings.'),
    if (AppConfig.showSubscriptions) _Para('If you buy a paid plan, payment is handled by our payment provider. We store your plan, invoices and billing details you enter. We do not store your full card number.', lead: 'Billing information.'),
  ]),
  _Sec('How we use it', [
    _Para('To provide transcription, save your sessions and let you share them.', bullet: true),
    if (AppConfig.showSubscriptions)
      _Para('To count your minutes and enforce plan limits, including the 30-minute limit on each free session.', bullet: true)
    else
      _Para('To count your minutes and enforce usage limits.', bullet: true),
    _Para('To send account emails: verification, password reset and billing notices.', bullet: true),
    _Para('To keep the service secure, prevent abuse and fix problems.', bullet: true),
  ]),
  _Sec('Sharing your transcripts', [
    _Para('Your transcripts are private to your account. If you turn on a live share link, anyone who has that link can read that session’s transcript until you turn sharing off. Treat the link like a password.'),
    _Para('Viewers who open a link are not billed and do not need an account.'),
  ]),
  _Sec('Who helps us run ScriptLiv', [
    _Para('We use a small number of service providers, only for what they are needed for:'),
    _Para('to send you account emails (Resend and Gmail). They receive your email address and the message.', lead: 'Email delivery', bullet: true),
    if (AppConfig.showSubscriptions) _Para('our payment provider takes payment for paid plans.', lead: 'Payments', bullet: true),
    _Para('to store your account and transcripts.', lead: 'Database and hosting', bullet: true),
    _Para('We do not sell your personal information, and we do not use your transcripts to advertise to you.'),
  ]),
  _Sec('How long we keep things', [
    _Para('We keep your account and transcripts until you delete them. Deleting a transcript removes its text from our systems. Usage and billing records are kept as billing history, without transcript content, as long as the law and our accounting require.'),
    _Para('You can delete your account in Settings, or email us at $_contactEmail.'),
  ]),
  _Sec('Security', [
    _Para('We protect data in transit with encryption, hash passwords, and limit who can reach our systems. No system is perfectly secure, so please use a strong, unique password and keep share links to people you trust.'),
  ]),
  _Sec('Your choices', [
    _Para('You can see and edit your name and email in Settings, delete any transcript from your history, turn share links on or off, and ask us for a copy of your data or to delete your account. Depending on where you live, you may have further rights under local law. Email $_contactEmail and we will help.'),
  ]),
  _Sec('Children', [
    _Para('ScriptLiv is not meant for children under 13, and we do not knowingly collect their information. If you think a child has given us data, tell us and we will remove it.'),
  ]),
  _Sec('Changes to this policy', [
    _Para('If we change this policy in a meaningful way, we will update the date above and, for significant changes, tell you by email or in the app.'),
  ]),
  _Sec('Contact us', [
    _Para('Questions about privacy? Email $_contactEmail.'),
  ]),
];

const _terms = [
  _Sec('The service', [
    _Para('ScriptLiv provides real-time speech-to-text transcription on the web and in our mobile app. Transcription is produced automatically and can contain mistakes. Please check anything important before you rely on it, especially for legal, medical or safety decisions.'),
  ]),
  _Sec('Your account', [
    _Para('You must give accurate details and verify your email address before you can record.', bullet: true),
    _Para('You are responsible for what happens under your account, so keep your password private.', bullet: true),
    _Para('You must be at least 13 years old, or the age of digital consent where you live.', bullet: true),
    _Para('Tell us right away at $_contactEmail if you think someone else has accessed your account.', bullet: true),
  ]),
  if (AppConfig.showSubscriptions)
    _Sec('Plans, minutes and limits', [
      _Para('includes 300 minutes every month. Each free session can run for up to 30 minutes. When a session reaches 30 minutes it stops, your transcript is saved, and you can start a new session while you still have minutes left.', lead: 'Basic (free)'),
      _Para('includes 2,500 minutes every month, with no per-session time limit. Extra minutes can be bought as add-ons and are valid until the end of the period they were bought in.', lead: 'Pro'),
      _Para('Minutes are counted as the seconds you actually speak into a session. Unused monthly minutes do not roll over. You can set your own personal limit in Settings. We may change plan details with notice; changes do not affect minutes you have already paid for.'),
    ])
  else
    _Sec('Minutes and limits', [
      _Para('ScriptLiv is currently free to use. Each account has an allowance of transcription minutes, shown in Settings, and sessions can have a maximum length. When a session reaches its limit it stops and your transcript is saved. You can start a new session while you still have minutes left.'),
      _Para('Minutes are counted as the seconds you actually speak into a session. You can set your own personal limit in Settings. We may change allowances and limits with notice. If we ever introduce paid features, we will tell you first and they will not apply to what you have already used.'),
    ]),
  if (AppConfig.showSubscriptions)
    _Sec('Payments', [
      _Para('Paid plans renew monthly until you cancel. You can cancel in the app and keep Pro until the end of the period you paid for. Payments are processed by our payment provider and prices are shown before you pay.'),
      _Para('If a payment fails, we will tell you and give you a chance to fix it. Until it is fixed, your account falls back to the free Basic allowance. Except where the law says otherwise, payments are not refundable once minutes have been used.'),
    ]),
  _Sec('Your content', [
    _Para('You own what you say and the transcripts made from it. You give us permission to process your audio and store your transcripts only so we can run the service for you.'),
    _Para('Only record people who know they are being recorded, and follow the laws on recording where you are. You are responsible for getting any consent needed. If you share a transcript through a link, you are responsible for who you give that link to.'),
  ]),
  _Sec('Acceptable use', [
    _Para('Please do not:'),
    _Para('use ScriptLiv for anything unlawful, harassing or harmful;', bullet: true),
    _Para('record people secretly or without a legal right to do so;', bullet: true),
    _Para('try to break, overload, probe or bypass the limits of the service;', bullet: true),
    _Para('share your account, or resell access, without our written permission;', bullet: true),
    _Para('use automated means to create accounts or drain free minutes.', bullet: true),
    _Para('We may pause or close accounts that break these rules.'),
  ]),
  _Sec('Availability', [
    _Para('We work hard to keep ScriptLiv running, but we cannot promise it will always be available or error-free. We may update or change features, and sometimes need to pause the service for maintenance.'),
  ]),
  _Sec('Liability', [
    _Para('ScriptLiv is provided “as is”. To the extent the law allows, Snypar Tech is not liable for indirect or consequential losses, or for losses caused by transcription errors, and our total liability for any claim is limited to the amount you paid us in the 12 months before it. Nothing here limits rights you have by law that cannot be limited.'),
  ]),
  _Sec('Ending your account', [
    _Para('You can stop using ScriptLiv at any time and delete your account in Settings. We may suspend or end your access if you break these terms or the law. How we handle your data is explained in our Privacy Policy.'),
  ]),
  _Sec('Changes to these terms', [
    _Para('We may update these terms. When we do, we will change the date above, and for significant changes we will tell you in the app or by email. Using ScriptLiv after a change means you accept the new terms.'),
  ]),
  _Sec('Contact us', [
    _Para('Questions about these terms? Email $_contactEmail.'),
  ]),
];

class LegalScreen extends StatelessWidget {
  final bool privacy;
  const LegalScreen({super.key, required this.privacy});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final sections = privacy ? _privacy : _terms;
    final title = privacy ? 'Privacy Policy' : 'Terms & Conditions';
    final intro = privacy
        ? 'ScriptLiv turns speech into text in real time. This policy explains what we collect to do that, what we do with it, and the choices you have. Snypar Tech (“we”, “us”) operates ScriptLiv.'
        : 'These terms are the agreement between you and Snypar Tech for using ScriptLiv. By creating an account or using the service, you agree to them. If you do not agree, please do not use ScriptLiv.';
    return _screen(
      context,
      title,
      ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          Text('Last updated 11 November 2026', style: TextStyle(fontSize: 12, color: c.textSecondary)),
          const SizedBox(height: 10),
          Text(intro, style: TextStyle(height: 1.4, color: c.textPrimary)),
          for (final s in sections) ...[
            const SizedBox(height: 20),
            Text(s.title, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: c.textPrimary)),
            const SizedBox(height: 6),
            for (final p in s.body)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (p.bullet) Padding(padding: const EdgeInsets.only(right: 8, left: 4), child: Text('•', style: TextStyle(color: c.textPrimary))),
                    Expanded(
                      child: Text.rich(
                        TextSpan(
                          children: [
                            if (p.lead != null) TextSpan(text: '${p.lead} ', style: const TextStyle(fontWeight: FontWeight.w700)),
                            TextSpan(text: p.text),
                          ],
                        ),
                        style: TextStyle(height: 1.4, color: c.textPrimary),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}

// ------------------------------------------------------------------ Payment history

class PaymentHistoryScreen extends StatefulWidget {
  const PaymentHistoryScreen({super.key});
  @override
  State<PaymentHistoryScreen> createState() => _PaymentHistoryScreenState();
}

class _PaymentHistoryScreenState extends State<PaymentHistoryScreen> {
  late Future<List<Map<String, dynamic>>> _future = PlatformApi.payments();

  static String _date(num seconds) {
    final d = DateTime.fromMillisecondsSinceEpoch(seconds.toInt() * 1000);
    const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${d.day} ${m[d.month - 1]} ${d.year}';
  }

  static String _money(num cents, String currency) {
    final value = cents / 100;
    final text = cents % 100 == 0 ? value.toStringAsFixed(0) : value.toStringAsFixed(2);
    return currency.toLowerCase() == 'inr' ? '₹$text' : '$text ${currency.toUpperCase()}';
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return _screen(
      context,
      'Payment history',
      FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snap.hasError) {
            return Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text('Could not load payments.', style: TextStyle(color: c.recordRed)),
                TextButton(onPressed: () => setState(() => _future = PlatformApi.payments()), child: const Text('Retry')),
              ]),
            );
          }
          final rows = snap.data ?? const [];
          if (rows.isEmpty) return Center(child: Text('No payments yet.', style: TextStyle(color: c.textSecondary)));
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: rows.length,
            separatorBuilder: (_, _) => Divider(height: 1, color: c.cardBorder),
            itemBuilder: (context, i) {
              final p = rows[i];
              final paid = p['status'] == 'paid';
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Row(children: [
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${p['description'] ?? 'Payment'}', style: TextStyle(fontWeight: FontWeight.w700, color: c.textPrimary)),
                      const SizedBox(height: 2),
                      Text(_date((p['created_at'] as num?) ?? 0), style: TextStyle(fontSize: 12, color: c.textSecondary)),
                    ]),
                  ),
                  Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                    Text(_money((p['amount_cents'] as num?) ?? 0, p['currency'] as String? ?? 'inr'),
                        style: TextStyle(fontWeight: FontWeight.w800, color: c.textPrimary)),
                    const SizedBox(height: 2),
                    Text('${p['status']}', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: paid ? c.liveGreen : c.textSecondary)),
                  ]),
                  if (p['receipt_url'] != null)
                    IconButton(
                      tooltip: 'Receipt',
                      icon: Icon(Icons.receipt_long_outlined, color: c.primaryBlue),
                      onPressed: () => launchUrl(Uri.parse(p['receipt_url'] as String), mode: LaunchMode.externalApplication),
                    ),
                ]),
              );
            },
          );
        },
      ),
    );
  }
}
