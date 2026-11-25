import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:st_transcribe/screens/platform_session_screen.dart';
import 'package:st_transcribe/services/platform_api.dart';
import 'package:st_transcribe/theme.dart';

List<String> _lines(int n) => [for (var i = 0; i < n; i++) 'Line $i of the live transcript, long enough to be a real sentence.'];

Future<void> _open(WidgetTester t, Future<SharedView> Function(String) fetcher) async {
  await t.pumpWidget(MaterialApp(theme: appTheme, home: SharedViewScreen(token: 'tok', fetcher: fetcher)));
  await _settle(t);
}

/// Lets a poll resolve, the frame build, the 200 ms follow animation and its settle step run (< 1 s, so no second poll).
Future<void> _settle(WidgetTester t) async {
  await t.pump(); // fetch resolves, setState
  await t.pump(); // frame built, post-frame follow starts
  await t.pump(const Duration(milliseconds: 300)); // animateTo finishes
  await t.pump(const Duration(milliseconds: 300)); // settle jump
}

Offset _slide(WidgetTester t) => t.widget<AnimatedSlide>(find.byType(AnimatedSlide)).offset;

ScrollController _ctrl(WidgetTester t) => t.widget<ListView>(find.byType(ListView)).controller!;

ScrollPosition _pos(WidgetTester t) => _ctrl(t).position;

Future<void> _close(WidgetTester t) async {
  await t.pumpWidget(const SizedBox()); // dispose: cancels the poll timer
}

void main() {
  testWidgets('header is clipped to the viewer area, so a hidden header cannot paint into the status bar', (t) async {
    await _open(t, (_) async => SharedView('T', false, _lines(60)));
    final clip = find.ancestor(of: find.byType(AnimatedSlide), matching: find.byType(ClipRect)).first;
    final area = t.getRect(clip);

    await t.drag(find.byType(ListView), const Offset(0, -300)); // user scrolls down
    await t.pump(const Duration(milliseconds: 400));

    expect(_slide(t), const Offset(0, -1), reason: 'header slid away');
    // The slid-away header sits fully above the clip area; the ClipRect is what keeps it from painting there.
    final laid = t.getRect(find.byType(AnimatedSlide)); // layout rect; the slide is a paint-time translation
    expect(laid.bottom + _slide(t).dy * laid.height, lessThanOrEqualTo(area.top + 0.5));
    final clipper = t.renderObject<RenderClipRect>(clip);
    expect(clipper.clipBehavior, isNot(Clip.none));
    expect(clipper.clipper, isNull, reason: 'clips to the Stack bounds');
    await _close(t);
  });

  testWidgets('user scrolling down hides the header and scrolling up shows it again', (t) async {
    await _open(t, (_) async => SharedView('T', false, _lines(60)));
    expect(_slide(t), Offset.zero);

    await t.drag(find.byType(ListView), const Offset(0, -300));
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), const Offset(0, -1));

    await t.drag(find.byType(ListView), const Offset(0, 120));
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), Offset.zero);
    await _close(t);
  });

  testWidgets('programmatic auto-follow scrolling does not hide the header', (t) async {
    var polls = 0;
    await _open(t, (_) async => SharedView('T', true, _lines(40 + 5 * polls++)));
    // First poll ran the follow animation to the bottom: a large downward scroll with no finger.
    expect(_pos(t).pixels, greaterThan(100));
    expect(_slide(t), Offset.zero, reason: 'auto-follow must not hide the header');

    // Further live updates keep following; header still stays.
    for (var i = 0; i < 3; i++) {
      await t.pump(const Duration(seconds: 1)); // next poll fires
      await _settle(t);
      expect(_slide(t), Offset.zero);
    }
    await _close(t);
  });

  testWidgets('auto-follow still tracks the newest text', (t) async {
    var polls = 0;
    // Two growing polls, then a quiet one (ListView only estimates the extent of unbuilt rows, so the
    // last step lands exactly on the end once nothing new arrives).
    await _open(t, (_) async => SharedView('T', true, _lines(40 + 10 * (polls++ < 2 ? polls - 1 : 1))));
    final first = _pos(t).pixels;
    await t.pump(const Duration(seconds: 1)); // poll with 10 new lines
    await _settle(t);
    expect(_pos(t).pixels, greaterThan(first), reason: 'followed the new lines');
    await t.pump(const Duration(seconds: 1)); // quiet poll
    await _settle(t);
    final p = _pos(t);
    expect(p.pixels, closeTo(p.maxScrollExtent, 2), reason: 'pinned to the newest text');
    await _close(t);
  });

  testWidgets('user scroll after auto-follow still hides the header, and pausing follow is respected', (t) async {
    var polls = 0;
    await _open(t, (_) async => SharedView('T', true, _lines(60 + 5 * polls++)));
    expect(_slide(t), Offset.zero);

    await t.drag(find.byType(ListView), const Offset(0, 400)); // scroll up to re-read
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), Offset.zero, reason: 'scrolling up keeps/shows the header');
    final held = _pos(t).pixels;

    await t.pump(const Duration(seconds: 1)); // next poll fires
    await _settle(t);
    expect(_pos(t).pixels, closeTo(held, 1), reason: 'follow paused while the user is reading above');

    await t.drag(find.byType(ListView), const Offset(0, -200)); // user scrolls down
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), const Offset(0, -1));
    await _close(t);
  });

  testWidgets('a fling keeps counting as user scrolling after the finger lifts', (t) async {
    await _open(t, (_) async => SharedView('T', false, _lines(200)));
    expect(_slide(t), Offset.zero);

    // Slow, small drag steps (5 px each, below the 6 px hide threshold) with a release velocity high enough to fling.
    final g = await t.startGesture(t.getCenter(find.byType(ListView)));
    var ms = 0;
    for (var i = 0; i < 12; i++) {
      ms += 8;
      await g.moveBy(const Offset(0, -5), timeStamp: Duration(milliseconds: ms));
    }
    await t.pump(); // rebuild with whatever the scroll notifications decided
    expect(_slide(t), Offset.zero, reason: 'the finger-driven part alone never crossed the hide threshold');
    final atLift = _pos(t).pixels;
    await g.up(timeStamp: Duration(milliseconds: ms));

    for (var i = 0; i < 12; i++) {
      await t.pump(const Duration(milliseconds: 16));
    }
    expect(_pos(t).pixels, greaterThan(atLift + 50), reason: 'the fling carried on after the finger lifted');
    expect(_slide(t), const Offset(0, -1), reason: 'the post-lift fling is still the user\'s scroll, so the header hides');

    await t.pumpAndSettle(); // fling ends; the next programmatic scroll must not count as the user's
    final hiddenAt = _pos(t).pixels;
    expect(hiddenAt, greaterThan(100));
    _ctrl(t).jumpTo(20); // large programmatic jump back up, but still below the top-of-list threshold
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), const Offset(0, -1), reason: 'user-scroll flag is cleared once the fling ends');
    await _close(t);
  });

  testWidgets('the user can interrupt an auto-follow animation; the view stays where they put it', (t) async {
    var polls = 0;
    await _open(t, (_) async => SharedView('T', true, _lines(60 + 20 * polls++)));
    final settled = _pos(t).pixels;

    await t.pump(const Duration(seconds: 1)); // next poll fires
    await t.pump(); // resolves, 20 more lines
    await t.pump(); // frame built, follow animation starts
    await t.pump(const Duration(milliseconds: 60)); // mid-animation
    final mid = _pos(t).pixels;
    expect(mid, greaterThan(settled), reason: 'follow animation is running');
    expect(_pos(t).pixels, lessThan(_pos(t).maxScrollExtent - 1), reason: 'and has not reached the end yet');

    final g = await t.startGesture(t.getCenter(find.byType(ListView))); // finger lands mid-animation
    await g.moveBy(const Offset(0, 40));
    await g.moveBy(const Offset(0, 200));
    await t.pump();
    await g.up();
    await t.pump(const Duration(milliseconds: 500)); // anything the follow logic does on cancel would have happened by now
    final after = _pos(t).pixels;
    expect(after, lessThan(mid), reason: 'finger moved the view up, away from the newest text');
    expect(_pos(t).maxScrollExtent - after, greaterThan(100), reason: 'follow did not yank the view back to the end');
    expect(_slide(t), Offset.zero, reason: 'scrolling up keeps the header');
    await _close(t);
  });

  testWidgets('after an interruption follow stays paused, then resumes once the user is back at the bottom', (t) async {
    var polls = 0;
    await _open(t, (_) async => SharedView('T', true, _lines(60 + 20 * polls++)));

    await t.pump(const Duration(seconds: 1));
    await t.pump();
    await t.pump();
    await t.pump(const Duration(milliseconds: 60));
    await t.drag(find.byType(ListView), const Offset(0, 300)); // interrupt the animation, read older text
    await t.pump(const Duration(milliseconds: 500));
    final reading = _pos(t).pixels;

    for (var i = 0; i < 2; i++) {
      await t.pump(const Duration(seconds: 1)); // more live text arrives
      await _settle(t);
      expect(_pos(t).pixels, closeTo(reading, 1), reason: 'follow stays paused while the user reads above');
    }

    for (var i = 0; i < 8 && _pos(t).extentAfter >= 80; i++) {
      await t.drag(find.byType(ListView), const Offset(0, -5000)); // user scrolls back towards the end
      await t.pumpAndSettle(const Duration(milliseconds: 100));
    }
    final p = _pos(t);
    expect(p.maxScrollExtent - p.pixels, lessThan(80), reason: 'near the end, which is what re-enables follow');
    final before = p.pixels;

    await t.pump(const Duration(seconds: 1)); // next poll: more text
    await _settle(t);
    expect(_pos(t).pixels, greaterThan(before), reason: 'follow resumed and tracks the new text');
    await _close(t);
  });

  testWidgets('header follows the user only: programmatic scrolls neither hide nor reveal it', (t) async {
    await _open(t, (_) async => SharedView('T', false, _lines(200)));

    _ctrl(t).jumpTo(600); // large programmatic scroll down
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), Offset.zero, reason: 'programmatic scroll down does not hide');

    await t.drag(find.byType(ListView), const Offset(0, -300)); // user scroll down hides
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), const Offset(0, -1));

    _ctrl(t).jumpTo(_pos(t).pixels - 300); // programmatic scroll up
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), const Offset(0, -1), reason: 'programmatic scroll up does not reveal');
    unawaited(_ctrl(t).animateTo(_pos(t).pixels - 100, duration: const Duration(milliseconds: 200), curve: Curves.easeOut));
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), const Offset(0, -1), reason: 'nor does an animated programmatic scroll');

    await t.drag(find.byType(ListView), const Offset(0, 100)); // user scroll up reveals
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), Offset.zero);

    await t.drag(find.byType(ListView), const Offset(0, -300)); // hide again
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), const Offset(0, -1));
    _ctrl(t).jumpTo(0); // reaching the very top always shows it
    await t.pump(const Duration(milliseconds: 400));
    expect(_slide(t), Offset.zero);
    await _close(t);
  });
}
