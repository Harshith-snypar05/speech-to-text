import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../config/app_config.dart';
import '../services/auth_service.dart';
import '../services/platform_api.dart';
import '../theme.dart';
import 'help_screens.dart';

/// Account / password / usage / limits / billing sections: the same settings the website exposes, backed by the same API.

String _fmtDate(num seconds) {
  final d = DateTime.fromMillisecondsSinceEpoch(seconds.toInt() * 1000);
  const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${d.day} ${m[d.month - 1]} ${d.year}';
}

String _fmtDateTime(DateTime d) {
  const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${d.day} ${m[d.month - 1]} ${d.year}';
}

String _fmtMinutes(double seconds) => '${(seconds / 60).floor()} min';

Future<void> _openWeb(String path) async {
  await launchUrl(Uri.parse('${AppConfig.webOrigin}$path'), mode: LaunchMode.externalApplication);
}

/// Card with a title, used for every section so the screen reads like the website's Settings page.
class SettingsSection extends StatelessWidget {
  final String title;
  final List<Widget> children;
  const SettingsSection({super.key, required this.title, required this.children});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    // Flat, full-width section (no card): grey title, rows 20px from the screen edges, a thick band between sections.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(height: 8, color: c.neutralChipBg),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: TextStyle(fontWeight: FontWeight.w500, fontSize: 14, color: c.textSecondary)),
              const SizedBox(height: 8),
              ...children,
            ],
          ),
        ),
      ],
    );
  }
}

/// Standard chevron (same size as before), shifted so the glyph's right edge lands on the row's right edge.
class SettingsChevron extends StatelessWidget {
  final Color? color;
  const SettingsChevron({super.key, this.color});
  @override
  Widget build(BuildContext context) {
    final col = color ?? AppColors.of(context).textSecondary;
    return Transform.translate(offset: const Offset(8, 0), child: Icon(Icons.chevron_right, size: 22, color: col));
  }
}

class _Note extends StatelessWidget {
  final String text;
  final bool error;
  const _Note(this.text, {this.error = false});
  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Text(text, style: TextStyle(fontSize: 13, color: error ? c.recordRed : c.textSecondary)),
    );
  }
}

class _Badge extends StatelessWidget {
  final String label;
  final Color color;
  const _Badge(this.label, this.color);
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(20)),
        child: Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color)),
      );
}

InputDecoration _field(String label, {String? hint}) =>
    InputDecoration(labelText: label, hintText: hint, border: const OutlineInputBorder(), isDense: true);

/// Tappable row used inside sections: label on the left, optional value, chevron or custom trailing widget.
class SettingsTile extends StatelessWidget {
  final String label;
  final String? value;
  final Widget? trailing;
  final VoidCallback? onTap;
  final Color? labelColor;
  final bool chevron;
  const SettingsTile({super.key, required this.label, this.value, this.trailing, this.onTap, this.labelColor, this.chevron = false});

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 13),
        child: Row(
          children: [
            Expanded(
              flex: 0,
              child: Text(label, style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14, color: labelColor ?? c.textPrimary)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: value == null
                  ? const SizedBox.shrink()
                  : Text(value!, textAlign: TextAlign.right, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 14, color: c.textSecondary)),
            ),
            if (trailing != null) ...[const SizedBox(width: 6), trailing!],
            if (chevron) ...[const SizedBox(width: 4), const SettingsChevron()],
          ],
        ),
      ),
    );
  }
}

Widget _divider(BuildContext context) => Divider(height: 1, color: AppColors.of(context).cardBorder);

// ---------------------------------------------------------------- Account details

class AccountSection extends StatefulWidget {
  const AccountSection({super.key});
  @override
  State<AccountSection> createState() => _AccountSectionState();
}

class _AccountSectionState extends State<AccountSection> {
  Map<String, dynamic>? _user;
  bool _loading = true;
  String? _note;
  bool _noteError = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final u = await PlatformApi.me();
      if (!mounted) return;
      setState(() {
        _user = u;
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _editName() async {
    final current = (_user?['name'] as String?) ?? '';
    final saved = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _EditNameDialog(initial: current),
    );
    if (saved != null && mounted) {
      setState(() {
        _user = saved;
        _note = 'Name saved.';
        _noteError = false;
      });
    }
  }

  Future<void> _resend() async {
    try {
      await PlatformApi.resendVerification();
      if (mounted) {
        setState(() {
          _note = 'Verification email sent. Open the link in it, then come back.';
          _noteError = false;
        });
      }
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _note = e.message;
          _noteError = true;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _note = 'Could not reach the server. Try again.';
          _noteError = true;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    if (_loading) {
      return const SettingsSection(title: 'Account details', children: [LinearProgressIndicator()]);
    }
    final u = _user;
    final name = (u?['name'] as String?) ?? '';
    final email = (u?['email'] as String?) ?? AuthService.currentEmail.value ?? '';
    final verified = u?['email_verified'] != false;
    final pending = u?['pending_email'] as String?;
    return SettingsSection(
      title: 'Account details',
      children: [
        SettingsTile(
          label: 'Name',
          value: name.isEmpty ? '-' : name,
          onTap: _editName,
          trailing: Icon(Icons.edit_outlined, size: 20, color: c.primaryBlue),
        ),
        _divider(context),
        SettingsTile(
          label: 'Email',
          value: email,
          trailing: _Badge(verified ? 'Verified' : 'Not verified', verified ? c.liveGreen : c.recordRed),
        ),
        if (pending != null) _Note('Waiting for you to verify $pending.'),
        if (!verified || pending != null)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(onPressed: _resend, child: const Text('Resend verification email')),
          ),
        if (_note != null) _Note(_note!, error: _noteError),
      ],
    );
  }
}

class _EditNameDialog extends StatefulWidget {
  final String initial;
  const _EditNameDialog({required this.initial});
  @override
  State<_EditNameDialog> createState() => _EditNameDialogState();
}

class _EditNameDialogState extends State<_EditNameDialog> {
  late final TextEditingController _name = TextEditingController(text: widget.initial);
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _error = 'Enter your name.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final user = await PlatformApi.updateName(name);
      if (mounted) Navigator.of(context).pop(user);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not reach the server. Try again.');
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return AlertDialog(
      title: const Text('Edit name'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _name,
            autofocus: true,
            decoration: _field('Name'),
            textCapitalization: TextCapitalization.words,
            onSubmitted: (_) => _busy ? null : _save(),
          ),
          if (_error != null) _Note(_error!, error: true),
        ],
      ),
      actions: [
        TextButton(onPressed: _busy ? null : () => Navigator.of(context).pop(), child: Text('Cancel', style: TextStyle(color: c.textSecondary))),
        FilledButton(onPressed: _busy ? null : _save, child: Text(_busy ? 'Saving...' : 'Save')),
      ],
    );
  }
}

// ---------------------------------------------------------------- Password (via emailed reset link)

class PasswordSection extends StatelessWidget {
  const PasswordSection({super.key});

  @override
  Widget build(BuildContext context) {
    return SettingsSection(
      title: 'Security',
      children: [
        SettingsTile(
          label: 'Change password',
          chevron: true,
          onTap: () => showDialog<void>(context: context, builder: (_) => const _ResetPasswordDialog()),
        ),
      ],
    );
  }
}

/// Same flow as "Forgot password" on the login page: a reset link goes to the account's email, and the new password is chosen there.
class _ResetPasswordDialog extends StatefulWidget {
  const _ResetPasswordDialog();
  @override
  State<_ResetPasswordDialog> createState() => _ResetPasswordDialogState();
}

class _ResetPasswordDialogState extends State<_ResetPasswordDialog> {
  final _email = TextEditingController(text: AuthService.currentEmail.value ?? '');
  bool _busy = false;
  bool _sent = false;
  String? _message;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final email = _email.text.trim();
    if (email.isEmpty || !email.contains('@')) {
      setState(() => _message = 'Enter your email address.');
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final msg = await PlatformApi.forgotPassword(email);
      if (mounted) {
        setState(() {
          _sent = true;
          _message = msg;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _message = e.message);
    } catch (_) {
      if (mounted) setState(() => _message = 'Could not reach the server. Try again.');
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return AlertDialog(
      title: Text(_sent ? 'Check your email' : 'Change password'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!_sent) ...[
            Text('To keep your account safe we email you a link to choose a new password.', style: TextStyle(color: c.textSecondary, fontSize: 13)),
            const SizedBox(height: 14),
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              decoration: _field('Email'),
              onSubmitted: (_) => _busy ? null : _send(),
            ),
          ] else
            Row(children: [
              Icon(Icons.mark_email_read_outlined, color: c.liveGreen),
              const SizedBox(width: 10),
              Expanded(child: Text(_message ?? 'Reset link sent.', style: TextStyle(color: c.textPrimary))),
            ]),
          if (!_sent && _message != null) _Note(_message!, error: true),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: Text(_sent ? 'Done' : 'Cancel', style: TextStyle(color: c.textSecondary)),
        ),
        if (!_sent) FilledButton(onPressed: _busy ? null : _send, child: Text(_busy ? 'Sending...' : 'Send reset link')),
      ],
    );
  }
}

// ---------------------------------------------------------------- Usage

class UsageSection extends StatefulWidget {
  const UsageSection({super.key});
  @override
  State<UsageSection> createState() => _UsageSectionState();
}

class _UsageSectionState extends State<UsageSection> {
  late Future<UsageInfo> _future = PlatformApi.usage();

  Widget _stat(AppColors c, String label, String value, {String? hint}) => Expanded(
        child: Container(
          margin: const EdgeInsets.only(right: 8),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(color: c.neutralChipBg, borderRadius: BorderRadius.circular(10)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: TextStyle(fontSize: 11, color: c.textSecondary)),
              const SizedBox(height: 2),
              Text(value, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: c.textPrimary)),
              if (hint != null) Text(hint, style: TextStyle(fontSize: 11, color: c.textSecondary)),
            ],
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return SettingsSection(
      title: 'Usage',
      children: [
        FutureBuilder<UsageInfo>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) return const LinearProgressIndicator();
            final u = snap.data;
            if (u == null) {
              return Row(children: [
                const Expanded(child: _Note('Could not load usage.', error: true)),
                TextButton(onPressed: () => setState(() => _future = PlatformApi.usage()), child: const Text('Retry')),
              ]);
            }
            if (u.offerActive) {
              final e = u.promoUntil;
              final total = u.offerMinutes > 0 ? u.offerMinutes : u.includedMinutes;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Inaugural offer: free minutes', style: TextStyle(fontWeight: FontWeight.w700, color: c.textPrimary)),
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: LinearProgressIndicator(value: (u.percentUsed / 100).clamp(0.0, 1.0), minHeight: 8),
                  ),
                  const SizedBox(height: 6),
                  Text('${_fmtMinutes(u.includedUsedSeconds)} of $total min used · ${_fmtMinutes(u.totalRemainingSeconds)} left',
                      style: TextStyle(fontSize: 13, color: c.textSecondary)),
                  _Note('Only the person speaking uses minutes. Viewers of a shared link are free.'
                      '${e != null ? ' The offer runs until ${e.year}-${e.month.toString().padLeft(2, '0')}-${e.day.toString().padLeft(2, '0')}.' : ''}'),
                ],
              );
            }
            if (!AppConfig.showSubscriptions) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Your minutes', style: TextStyle(fontWeight: FontWeight.w700, color: c.textPrimary)),
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: LinearProgressIndicator(value: (u.percentUsed / 100).clamp(0.0, 1.0), minHeight: 8),
                  ),
                  const SizedBox(height: 6),
                  Text('${_fmtMinutes(u.includedUsedSeconds)} of ${u.includedMinutes} min used · ${_fmtMinutes(u.totalRemainingSeconds)} left',
                      style: TextStyle(fontSize: 13, color: c.textSecondary)),
                  const _Note('Only the person speaking uses minutes. Viewers of a shared link are free. Contact support for more minutes.'),
                ],
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${u.planName} plan', style: TextStyle(fontWeight: FontWeight.w700, color: c.textPrimary)),
                const SizedBox(height: 8),
                ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: LinearProgressIndicator(value: (u.percentUsed / 100).clamp(0.0, 1.0), minHeight: 8),
                ),
                const SizedBox(height: 6),
                Text(
                  '${_fmtMinutes(u.includedUsedSeconds)} of ${u.includedMinutes} min used · ${_fmtMinutes(u.includedRemainingSeconds)} left',
                  style: TextStyle(fontSize: 13, color: c.textSecondary),
                ),
                const SizedBox(height: 10),
                Row(children: [
                  _stat(c, 'Included left', _fmtMinutes(u.includedRemainingSeconds), hint: 'of ${u.includedMinutes} min'),
                  _stat(c, 'Add-on balance', _fmtMinutes(u.addonRemainingSeconds),
                      hint: u.addonExpiresAt != null ? 'expires ${_fmtDateTime(u.addonExpiresAt!)}' : null),
                  _stat(c, 'Total available', _fmtMinutes(u.totalRemainingSeconds)),
                ]),
                const _Note('Only the person speaking uses minutes. Viewers of a shared link are free.'),
              ],
            );
          },
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------- Usage limits

class LimitsSection extends StatefulWidget {
  final ServerSettings settings;
  final Future<ServerSettings?> Function(Map<String, dynamic> patch) onSave;
  const LimitsSection({super.key, required this.settings, required this.onSave});
  @override
  State<LimitsSection> createState() => _LimitsSectionState();
}

class _LimitsSectionState extends State<LimitsSection> {
  late final TextEditingController _limit = TextEditingController(text: widget.settings.personalLimitMinutes?.toString() ?? '');
  bool _busy = false;
  String? _note;
  bool _noteError = false;

  @override
  void dispose() {
    _limit.dispose();
    super.dispose();
  }

  Future<void> _patch(Map<String, dynamic> patch, {String? ok}) async {
    setState(() {
      _busy = true;
      _note = null;
    });
    final r = await widget.onSave(patch);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _note = r == null ? 'Could not save. Try again.' : ok;
      _noteError = r == null;
    });
  }

  Future<void> _saveLimit() {
    final t = _limit.text.trim();
    int? v;
    if (t.isNotEmpty) {
      final n = double.tryParse(t);
      if (n == null) {
        setState(() {
          _note = 'Enter a number of minutes, or leave blank for no limit.';
          _noteError = true;
        });
        return Future.value();
      }
      v = n.floor() < 1 ? 1 : n.floor();
      _limit.text = '$v';
    }
    return _patch({'personal_limit_minutes': v}, ok: v == null ? 'Limit removed.' : 'Limit saved.');
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final s = widget.settings;
    return SettingsSection(
      title: 'Usage limits',
      children: [
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Usage warnings'),
          subtitle: const Text('Get a heads-up as you use up your minutes.'),
          value: s.usageWarnings,
          onChanged: _busy ? null : (v) => _patch({'usage_warnings': v}),
        ),
        Text('Warn me at', style: TextStyle(fontSize: 13, color: c.textSecondary)),
        const SizedBox(height: 6),
        Wrap(
          spacing: 8,
          children: [
            for (final p in const [50, 80, 100])
              FilterChip(
                label: Text('$p%'),
                selected: s.warnPercents.contains(p),
                onSelected: _busy || !s.usageWarnings
                    ? null
                    : (on) {
                        final next = {...s.warnPercents};
                        on ? next.add(p) : next.remove(p);
                        _patch({'warn_percents': (next.toList()..sort())});
                      },
              ),
          ],
        ),
        const SizedBox(height: 14),
        TextField(
          controller: _limit,
          decoration: _field('Personal monthly limit (minutes)', hint: 'Blank = no limit'),
          keyboardType: TextInputType.number,
        ),
        const SizedBox(height: 10),
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton(onPressed: _busy ? null : _saveLimit, child: const Text('Save limit')),
        ),
        if (_note != null) _Note(_note!, error: _noteError),
      ],
    );
  }
}


// ---------------------------------------------------------------- Membership

/// Bumped when cancel / keep / delete changes the plan so the Membership card reloads.
final ValueNotifier<int> _membershipTick = ValueNotifier(0);

class MembershipSection extends StatefulWidget {
  const MembershipSection({super.key});
  @override
  State<MembershipSection> createState() => _MembershipSectionState();
}

class _MembershipSectionState extends State<MembershipSection> {
  Map<String, dynamic>? _sub;
  Map<String, dynamic>? _pm;
  bool _loading = true;
  bool _offer = false;

  @override
  void initState() {
    super.initState();
    _load();
    _membershipTick.addListener(_load);
  }

  @override
  void dispose() {
    _membershipTick.removeListener(_load);
    super.dispose();
  }

  Future<Object?> _try(Future<Object?> f) async {
    try {
      return await f;
    } catch (_) {
      return null;
    }
  }

  Future<void> _load() async {
    final r = await Future.wait<Object?>([
      _try(PlatformApi.subscription()),
      _try(PlatformApi.paymentMethod()),
      _try(PlatformApi.usage()),
    ]);
    if (!mounted) return;
    setState(() {
      _offer = (r[2] as UsageInfo?)?.offerActive ?? false;
      _sub = (r[0] as Map<String, dynamic>?)?['subscription'] as Map<String, dynamic>?;
      _pm = r[1] as Map<String, dynamic>?;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    if (_loading) {
      return const SettingsSection(title: 'Membership details', children: [LinearProgressIndicator()]);
    }
    if (_offer) return const SizedBox.shrink(); // no plans, payments or billing while the inaugural offer runs
    final sub = _sub;
    if (sub == null) {
      return SettingsSection(
        title: 'Membership details',
        children: [
          const _Note('Could not load your membership.', error: true),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: () {
                setState(() => _loading = true);
                _load();
              },
              child: const Text('Retry'),
            ),
          ),
        ],
      );
    }
    final paid = sub['plan'] != 'basic';
    final payment = sub['payment'] as Map<String, dynamic>?;
    final cancelling = sub['cancel_at_period_end'] == true;
    final renews = (sub['renews_or_resets_at'] as num?) ?? 0;
    final price = (sub['price_display'] as String?) ??
        (sub['price_inr_month'] != null ? '₹${sub['price_inr_month']}${sub['tax_note'] != null ? ' ${sub['tax_note']}' : ''}' : '₹999 + GST');

    String statusText;
    Color statusColor;
    if (payment != null) {
      final restricted = payment['access_restricted'] == true;
      statusText = restricted ? 'Payment required' : 'Payment failed';
      statusColor = restricted ? c.recordRed : Colors.orange;
    } else if (cancelling) {
      statusText = 'Cancelled';
      statusColor = Colors.orange;
    } else {
      statusText = 'Active';
      statusColor = c.liveGreen;
    }

    String nextPayment;
    if (!paid) {
      nextPayment = 'None (free plan)';
    } else if (cancelling) {
      nextPayment = 'None (ends ${_fmtDate((sub['access_ends_at'] as num?) ?? renews)})';
    } else {
      nextPayment = '${_fmtDate(renews)} · $price';
    }

    final last4 = _pm?['last4'];
    final method = last4 != null ? '${_pm!['brand'] ?? 'Card'} ending $last4' : (paid ? 'No card on file' : '-');

    return SettingsSection(
      title: 'Membership details',
      children: [
        SettingsTile(
          label: 'Plan',
          value: '${sub['plan_name'] ?? ''}',
          trailing: _Badge(statusText, statusColor),
        ),
        _divider(context),
        SettingsTile(label: 'Next payment', value: nextPayment),
        _divider(context),
        SettingsTile(label: 'Payment method', value: method),
        _divider(context),
        SettingsTile(label: 'Change plan', chevron: true, onTap: () => _openWeb('/pricing')),
        _divider(context),
        SettingsTile(
          label: 'View payment history',
          chevron: true,
          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const PaymentHistoryScreen())),
        ),
        if (payment != null) _Note(payment['message'] as String? ?? 'There is a problem with your payment.', error: true),
      ],
    );
  }
}

/// Cancel membership + Delete account, shown just above Log out.
class AccountActionsSection extends StatefulWidget {
  const AccountActionsSection({super.key});
  @override
  State<AccountActionsSection> createState() => _AccountActionsSectionState();
}

class _AccountActionsSectionState extends State<AccountActionsSection> {
  Map<String, dynamic>? _sub;
  bool _busy = false;
  String? _note;
  bool _noteError = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!AppConfig.showSubscriptions) return; // no membership UI, so no need to fetch it
    try {
      final r = await PlatformApi.subscription();
      if (mounted) setState(() => _sub = r['subscription'] as Map<String, dynamic>?);
    } catch (_) {}
  }

  Future<void> _act(Future<void> Function() action, String ok) async {
    setState(() {
      _busy = true;
      _note = null;
    });
    var note = ok;
    var err = false;
    try {
      await action();
      final fresh = await PlatformApi.subscription();
      _sub = fresh['subscription'] as Map<String, dynamic>?;
      _membershipTick.value++;
    } on ApiException catch (e) {
      note = e.message;
      err = true;
    } catch (_) {
      note = 'Could not reach the server. Try again.';
      err = true;
    }
    if (mounted) {
      setState(() {
        _busy = false;
        _note = note;
        _noteError = err;
      });
    }
  }

  Future<bool> _confirm(String title, String body, String action, {bool danger = true}) async {
    final c = AppColors.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(body),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: Text('Not now', style: TextStyle(color: c.textSecondary))),
          FilledButton(
            style: danger ? FilledButton.styleFrom(backgroundColor: c.recordRed) : null,
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(action),
          ),
        ],
      ),
    );
    return ok == true;
  }

  Future<void> _cancelMembership() async {
    final renews = (_sub?['renews_or_resets_at'] as num?) ?? 0;
    final ok = await _confirm(
      'Cancel membership?',
      'You keep Pro until ${_fmtDate(renews)}. After that you move to the free Basic plan.',
      'Cancel membership',
    );
    if (ok) await _act(PlatformApi.cancelPlan, 'Membership cancelled. You keep access until the period ends.');
  }

  Future<void> _deleteAccount() async {
    final deleted = await showDialog<bool>(context: context, builder: (_) => const _DeleteAccountDialog());
    if (deleted == true) {
      await AuthService.logout();
      if (mounted) Navigator.of(context).popUntil((route) => route.isFirst);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final sub = _sub;
    final paid = AppConfig.showSubscriptions && sub != null && sub['plan'] != 'basic';
    final cancelling = sub?['cancel_at_period_end'] == true;
    return SettingsSection(
      title: 'Account',
      children: [
        if (paid) ...[
          if (cancelling)
            SettingsTile(
              label: 'Keep my membership',
              labelColor: c.primaryBlue,
              onTap: _busy ? null : () => _act(PlatformApi.resumePlan, 'Membership kept.'),
            )
          else
            SettingsTile(label: 'Cancel membership', labelColor: c.recordRed, onTap: _busy ? null : _cancelMembership),
          _divider(context),
        ],
        SettingsTile(label: 'Delete account', labelColor: c.recordRed, onTap: _deleteAccount),
        if (_note != null) _Note(_note!, error: _noteError),
      ],
    );
  }
}

class _DeleteAccountDialog extends StatefulWidget {
  const _DeleteAccountDialog();
  @override
  State<_DeleteAccountDialog> createState() => _DeleteAccountDialogState();
}

class _DeleteAccountDialogState extends State<_DeleteAccountDialog> {
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  Future<void> _delete() async {
    if (_password.text.isEmpty) {
      setState(() => _error = 'Enter your password to confirm.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await PlatformApi.deleteAccount(_password.text);
      if (mounted) Navigator.of(context).pop(true);
      return;
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not reach the server. Try again.');
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return AlertDialog(
      title: const Text('Delete account?'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('This permanently deletes your account, transcripts and usage. It cannot be undone.', style: TextStyle(color: c.textSecondary, fontSize: 13)),
          const SizedBox(height: 14),
          TextField(controller: _password, obscureText: true, decoration: _field('Your password'), onSubmitted: (_) => _busy ? null : _delete()),
          if (_error != null) _Note(_error!, error: true),
        ],
      ),
      actions: [
        TextButton(onPressed: _busy ? null : () => Navigator.of(context).pop(false), child: Text('Cancel', style: TextStyle(color: c.textSecondary))),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: c.recordRed),
          onPressed: _busy ? null : _delete,
          child: Text(_busy ? 'Deleting...' : 'Delete account'),
        ),
      ],
    );
  }
}
