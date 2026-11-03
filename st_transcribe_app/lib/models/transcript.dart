const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

String titleFromBody(String body) {
  final firstLine = body.trim().split('\n').first.trim();
  if (firstLine.isEmpty) return 'Untitled transcript';
  final words = firstLine.split(' ').take(6).join(' ');
  return words.length < firstLine.length ? '$words...' : words;
}

String previewFromBody(String body) {
  final text = body.trim().replaceAll('\n', ' ');
  return text.length > 60 ? '${text.substring(0, 60)}...' : text;
}

String formatDateLabel(DateTime date) => '${_months[date.month - 1]} ${date.day}, ${date.year}';

/// Lightweight listing info for a saved transcript -- title/preview/date
/// only, no body. What Home screen's Recent Transcripts list reads, so
/// showing the list doesn't require loading every transcript's full text
/// (see TranscriptStorage.listMeta).
class TranscriptMeta {
  final String id;
  final String title;
  final String preview;
  final DateTime date;

  const TranscriptMeta({required this.id, required this.title, required this.preview, required this.date});

  String get dateLabel => formatDateLabel(date);

  factory TranscriptMeta.fromBody({required String id, required String body, required DateTime date}) {
    return TranscriptMeta(id: id, title: titleFromBody(body), preview: previewFromBody(body), date: date);
  }

  Map<String, dynamic> toJson() => {'id': id, 'title': title, 'preview': preview, 'date': date.toIso8601String()};

  factory TranscriptMeta.fromJson(Map<String, dynamic> json) => TranscriptMeta(
        id: json['id'] as String,
        title: json['title'] as String,
        preview: json['preview'] as String,
        date: DateTime.parse(json['date'] as String),
      );
}

/// A saved transcript's full content. Backed by a real .txt file on native
/// platforms, by browser storage (+ a downloaded .txt) on web -- see
/// TranscriptStorage. Loaded on demand (opening a transcript, exporting
/// it) rather than eagerly for the whole list.
class Transcript {
  final String id;
  final String body;
  final DateTime date;

  Transcript({required this.id, required this.body, required this.date});

  TranscriptMeta get meta => TranscriptMeta.fromBody(id: id, body: body, date: date);

  String get title => titleFromBody(body);
  String get preview => previewFromBody(body);
  String get dateLabel => formatDateLabel(date);
}
