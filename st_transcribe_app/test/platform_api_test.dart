import 'package:flutter_test/flutter_test.dart';
import 'package:st_transcribe/services/platform_api.dart';

void main() {
  test('UsageInfo parses the usage payload and warnings', () {
    final u = UsageInfo.fromJson({
      'plan_name': 'Basic',
      'included_minutes': 300,
      'included_used_seconds': 600,
      'included_remaining_seconds': 17400,
      'addon_remaining_seconds': 0,
      'total_remaining_seconds': 17400,
      'percent_used': 3.3,
      'reset_at': 1800000000,
      'cancel_at_period_end': false,
      'warnings': [
        {'level': 80, 'message': 'You have used 80% of your minutes.'}
      ],
    });
    expect(u.planName, 'Basic');
    expect(u.includedMinutes, 300);
    expect(u.includedRemainingSeconds, 17400);
    expect(u.warnings, ['You have used 80% of your minutes.']);
  });

  test('SessionItem tolerates missing optional fields', () {
    final s = SessionItem.fromJson({'session_id': 'sess_1', 'title': '', 'started_at': null, 'ended_at': null, 'sharing': false});
    expect(s.id, 'sess_1');
    expect(s.startedAt, isNull);
    expect(s.transcript, isEmpty);
    expect(s.shareUrl, isNull);
  });

  test('SharedView reads live flag and lines', () {
    final v = SharedView.fromJson({'title': 'Talk', 'live': true, 'transcript': ['a', 'b']});
    expect(v.live, isTrue);
    expect(v.transcript, ['a', 'b']);
  });
}
